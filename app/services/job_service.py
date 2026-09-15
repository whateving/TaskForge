# Import IntegrityError exception to handle database constraint violations (e.g., unique key conflicts)
from sqlalchemy.exc import IntegrityError
# Import Session type for type-hinting SQLAlchemy database sessions
from sqlalchemy.orm import Session

# Import Job ORM model and JobStatus enum representing task data and states
from app.models.job import Job, JobStatus
# Import JobCreate Pydantic schema for validated input parameters
from app.schemas.job import JobCreate
# Import message queue service functions for pushing jobs to Redis and recovering DLQ tasks
from app.services.queue_service import enqueue_job, requeue_dead_letter_job

# Import datetime for timestamp comparisons
from datetime import datetime

# Import update construct for atomic SQL update operations
from sqlalchemy import update

# Scan database for retriable jobs whose exponential backoff delay has passed, and push them back into the queue
def requeue_due_jobs(db: Session) -> None:
    # Capture current UTC time to find jobs whose retry window has arrived
    now = datetime.utcnow()

    # Query all QUEUED jobs that have a scheduled retry timestamp on or before the current time
    due_jobs = (
        db.query(Job)
        .filter(
            Job.status == JobStatus.QUEUED,
            Job.next_retry_at.is_not(None),
            Job.next_retry_at <= now,
        )
        .all()
    )

    # Process each due job individually to safely re-enqueue and update state
    for job in due_jobs:
        try:
            # Re-push job ID to Redis stream for processing by workers
            enqueue_job(job.id)

            # Atomically clear next_retry_at to prevent duplicate re-enqueueing by concurrent scheduler loops
            result = db.execute(
                update(Job)
                .where(
                    Job.id == job.id,
                    Job.status == JobStatus.QUEUED,
                    Job.next_retry_at.is_not(None),
                    Job.next_retry_at <= now,
                )
                .values(next_retry_at=None)
            )

            # Commit if this thread successfully updated the job row; otherwise rollback
            if result.rowcount > 0:
                db.commit()
            else:
                db.rollback()

        except Exception:
            # Roll back current transaction on failure and re-raise exception
            db.rollback()
            raise

# Service function to manually recover a permanently FAILED job and move it back to the active queue
def requeue_failed_job(
    db: Session,
    job_id: int,
) -> Job | None:
    # Fetch target job by primary key ID
    job = db.get(Job, job_id)

    # Return None if the job ID does not exist in database
    if job is None:
        return None

    # Guard clause: return early without modifying if job is not in FAILED state
    if job.status != JobStatus.FAILED:
        return job

    # Reset job state back to QUEUED and clear any scheduled retry timestamps
    job.status = JobStatus.QUEUED
    job.next_retry_at = None

    # Save state changes to database and refresh model instance
    db.commit()
    db.refresh(job)

    # Remove task from Redis Dead Letter Queue and re-add to active Redis stream
    requeue_dead_letter_job(job.id)

    return job

# Service function to create a new job while ensuring strict idempotency and handling race conditions
def create_job(
    db: Session,
    job_data: JobCreate,
    idempotency_key: str,
) -> tuple[Job, bool]:
    # Check if a job with the given idempotency key was already submitted
    existing_job = (
        db.query(Job)
        .filter(Job.idempotency_key == idempotency_key)
        .first()
    )

    # If key exists, return existing job instance and False (indicating no new job was created)
    if existing_job is not None:
        return existing_job, False

    # Instantiate new Job ORM model with status initialized to QUEUED
    job = Job(
        type=job_data.type,
        payload=job_data.payload,
        status=JobStatus.QUEUED,
        idempotency_key=idempotency_key,
    )

    # Stage new job instance in active session
    db.add(job)
    """
    Why this exists: If two identical API requests hit the server at the exact same millisecond, both could pass Step 1.
    PostgreSQL's UNIQUE constraint on idempotency_key forces one request to fail with an IntegrityError.
    The Catch: If IntegrityError occurs, it rolls back the failed transaction, re-queries for the winning job that 
    was saved by the parallel request, and returns (existing_job, False).
    """
    try:
        # Attempt to save record to database
        db.commit()
    except IntegrityError:
        # Handle concurrent race condition where a parallel request inserted the same key first
        db.rollback()

        # Re-query for the winning job inserted by the parallel request
        existing_job = (
            db.query(Job)
            .filter(Job.idempotency_key == idempotency_key)
            .first()
        )

        # Re-raise error if failure was caused by a different integrity constraint
        if existing_job is None:
            raise

        # Return parallel-created job instance with False
        return existing_job, False

    db.refresh(job) # Refreshes job to populate the generated auto-incrementing job.id.

    # Push newly created job ID into Redis Stream
    enqueue_job(job.id)

    # Return created job instance and True (indicating new job was successfully created)
    return job, True


# Service function to retrieve a single job record by ID
def get_job(db: Session, job_id: int) -> Job | None:
    return db.get(Job, job_id)

# Service function to cancel a QUEUED job before workers pick it up
def cancel_job(
    db: Session,
    job_id: int,
) -> Job | None:
    # Fetch job instance from database
    job = db.get(Job, job_id)

    # Return None if job ID does not exist
    if job is None:
        return None

    # Only jobs currently in QUEUED status can be cancelled
    if job.status != JobStatus.QUEUED:
        return job

    # Update state to CANCELLED, commit transaction, and refresh object
    job.status = JobStatus.CANCELLED
    db.commit()
    db.refresh(job)

    return job