# Import standard library time module for simulation delays and execution timing
import time
# Import uuid module to generate unique identifier prefixes for worker process instances
import uuid
# Import datetime utilities for calculating exponential backoff retry schedules
from datetime import datetime, timedelta

# Import SQLAlchemy update construct for atomic state updates
from sqlalchemy import update
# Import PostgreSQL-specific insert dialect to support ON CONFLICT upsert operations
from sqlalchemy.dialects.postgresql import insert

# Import database session local factory
from app.db.database import SessionLocal
# Import ORM models for jobs and execution idempotency logs
from app.models.job import Job, JobStatus
from app.models.job_execution import JobExecution
# Import job service to sweep and requeue delayed jobs whose backoff timer expired
from app.services.job_service import requeue_due_jobs
# Import metrics service to record telemetry events
from app.services.metrics_service import record_metric
# Import Redis Stream operations for consumer group consumption, acknowledgement, and DLQ handling
from app.services.queue_service import (
    acknowledge_job,
    dequeue_job,
    ensure_consumer_group,
    move_to_dead_letter_queue,
)

# Import ThreadPoolExecutor to run job processing tasks concurrently
from concurrent.futures import ThreadPoolExecutor

# Maximum number of concurrent threads allowed to process tasks simultaneously in this worker process
MAX_CONCURRENT_JOBS = 3
# Generate a short 8-character hex string as a unique worker identifier
WORKER_ID = uuid.uuid4().hex[:8]


# Executes business logic and records side effects with PostgreSQL-level idempotency guarantees
def execute_job(job: Job, db) -> None:
    # First check: see if execution record already exists in job_executions table
    existing_execution = (
        db.query(JobExecution)
        .filter(JobExecution.job_id == job.id)
        .first()
    )

    # Return early if side effects were already executed previously
    if existing_execution is not None:
        print(
            f"[WORKER {WORKER_ID}] "
            f"Job {job.id} side effect already executed"
        )
        return

    print(
        f"[WORKER {WORKER_ID}] "
        f"Executing {job.type} for job {job.id}"
    )

    # Simulate heavy workload processing time (3 seconds)
    time.sleep(3)

    # Check payload for explicit simulated failure flag
    if job.payload.get("should_fail") is True:
        raise RuntimeError("Simulated job failure")

    # Construct atomic INSERT ON CONFLICT DO NOTHING query to guarantee exactly-once side-effect execution
    statement = (
        insert(JobExecution)
        .values(job_id=job.id)
        .on_conflict_do_nothing(
            index_elements=["job_id"]
        )
    )

    result = db.execute(statement)

    db.commit()

    # If rowcount is 0, a parallel worker recorded the execution first
    if result.rowcount == 0:
        print(
            f"[WORKER {WORKER_ID}] "
            f"Job {job.id} side effect already executed"
        )
        return

    print(
        f"[WORKER {WORKER_ID}] "
        f"Work finished for job {job.id}"
    )


# Computes exponential backoff delay (in seconds) based on current attempt count ($2^{attempt}$)
def calculate_retry_delay(attempt: int) -> int:
    return 2 ** attempt


# Atomically transitions a job's database status to PROCESSING and increments attempt counter
def claim_job(
    db,
    job_id: int,
    recovered: bool,
) -> Job | None:

    # Reclaimed/stale jobs expect status PROCESSING; fresh jobs expect status QUEUED
    if recovered:
        allowed_statuses = [JobStatus.PROCESSING]
    else:
        allowed_statuses = [JobStatus.QUEUED]

    # Perform atomic database update conditioned on job ID and allowed initial state
    result = db.execute(
        update(Job)
        .where(
            Job.id == job_id,
            Job.status.in_(allowed_statuses),
        )
        .values(
            status=JobStatus.PROCESSING,
            attempts=Job.attempts + 1,
            last_error=None,
        )
    )

    # Roll back and return None if another worker claimed or updated the job first
    if result.rowcount == 0:
        db.rollback()
        return None

    db.commit()

    # Fetch and return the updated job instance
    return db.get(Job, job_id)


# Worker task function that manages job claiming, execution, metrics tracking, retry backoff, and DLQ routing
def process_job(
    message_id: str,
    job_id: int,
    recovered: bool,
) -> None:

    # Create a fresh database session for this worker thread
    db = SessionLocal()

    try:
        # Fetch target job instance from PostgreSQL
        job = db.get(Job, job_id)

        # Acknowledge message and exit if job record no longer exists
        if job is None:
            print(
                f"[WORKER {WORKER_ID}] "
                f"Job {job_id} not found"
            )

            acknowledge_job(message_id)
            return

        # Attempt to claim ownership and transition status to PROCESSING
        job = claim_job(
            db,
            job_id,
            recovered,
        )

        # Exit if job was already claimed or processed elsewhere
        if job is None:
            print(
                f"[WORKER {WORKER_ID}] "
                f"Job {job_id} was already claimed "
                f"or already completed"
            )

            acknowledge_job(message_id)
            return

        print(
            f"[WORKER {WORKER_ID}] "
            f"Processing job {job.id} "
            f"(attempt {job.attempts}/{job.max_retries})"
        )

        # Record that the worker actually started processing.
        record_metric(
            db,
            job_id=job.id,
            event="processing",
        )

        # Track high-precision start timestamp
        start_time = time.perf_counter()

        # Execute core job logic
        execute_job(job, db)

        # Calculate total processing duration in milliseconds
        duration_ms = int(
            (time.perf_counter() - start_time) * 1000
        )

        # Mark job as COMPLETED and save to database
        job.status = JobStatus.COMPLETED
        db.commit()

        # Record completion metrics telemetry
        record_metric(
            db,
            job_id=job.id,
            event="completed",
            duration_ms=duration_ms,
        )

        # Acknowledge message in Redis Stream to remove it from Pending Entries List (PEL)
        acknowledge_job(message_id)

        print(
            f"[WORKER {WORKER_ID}] "
            f"Job {job.id} completed "
            f"in {duration_ms} ms"
        )

    except Exception as exc:

        print(
            f"[WORKER {WORKER_ID}] "
            f"Job {job_id} failed: {exc}"
        )

        # Refresh job record in error context
        job = db.get(Job, job_id)

        if job is None:
            acknowledge_job(message_id)
            return

        # Record error details
        job.last_error = str(exc)

        # If remaining retries exist, calculate exponential backoff delay and reschedule
        if job.attempts < job.max_retries:

            retry_delay = calculate_retry_delay(
                job.attempts
            )

            retry_at = datetime.utcnow() + timedelta(
                seconds=retry_delay
            )

            # Re-queue job state and schedule future retry timestamp
            job.status = JobStatus.QUEUED
            job.next_retry_at = retry_at

            db.commit()

            # Record retry metric event
            record_metric(
                db,
                job_id=job.id,
                event="retry",
            )

            # Acknowledge current Redis stream message since retry is scheduled via DB backoff
            acknowledge_job(message_id)

            print(
                f"[WORKER {WORKER_ID}] "
                f"Job {job.id} scheduled to retry at "
                f"{retry_at.isoformat()}"
            )

        # Max retries exhausted: mark FAILED and move task to Dead Letter Queue (DLQ)
        else:

            job.status = JobStatus.FAILED
            db.commit()

            # Record failure metric event
            record_metric(
                db,
                job_id=job.id,
                event="failed",
            )

            # Route failed job metadata into Redis DLQ stream
            move_to_dead_letter_queue(
                job_id=job.id,
                attempts=job.attempts,
                last_error=job.last_error,
                original_message_id=message_id,
            )

            # Acknowledge original message in primary queue
            acknowledge_job(message_id)

            print(
                f"[WORKER {WORKER_ID}] "
                f"Job {job.id} moved to dead letter queue "
                f"after {job.attempts} attempts"
            )

    finally:
        # Guarantee database session cleanup per worker task execution
        db.close()


# Main event loop running the worker service, scheduler, thread pool executor, and queue consumer
def run_worker() -> None:
    # Ensure worker consumer group exists in Redis Stream
    ensure_consumer_group()

    print(
        f"[WORKER {WORKER_ID}] "
        f"TaskForge worker started "
        f"with concurrency={MAX_CONCURRENT_JOBS}"
    )

    # Initialize thread pool executor managing concurrent worker tasks
    with ThreadPoolExecutor(
        max_workers=MAX_CONCURRENT_JOBS
    ) as executor:

        futures = set()

        # Infinite loop pulling jobs from Redis and processing them concurrently
        while True:
            # Remove completed tasks from the tracking set.
            completed_futures = {
                future
                for future in futures
                if future.done()
            }

            futures.difference_update(completed_futures)

            # Run the retry scheduler to re-enqueue jobs whose backoff delay timer expired
            db = SessionLocal()

            try:
                requeue_due_jobs(db)
            finally:
                db.close()

            # Don't pull more jobs when all worker threads are busy.
            if len(futures) >= MAX_CONCURRENT_JOBS:
                time.sleep(0.05)
                continue

            # Pull next available job from Redis stream (or claim stale unacknowledged messages)
            message = dequeue_job(WORKER_ID)

            if message is None:
                continue

            message_id, job_id, recovered = message

            # Submit task to thread pool executor for processing
            future = executor.submit(
                process_job,
                message_id,
                job_id,
                recovered,
            )

            # Track active thread future
            futures.add(future)


# Entry point guard executing worker loop when run as primary script
if __name__ == "__main__":
    run_worker()