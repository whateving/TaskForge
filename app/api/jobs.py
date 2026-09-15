# Import FastAPI components for route handling, dependencies, HTTP headers, exceptions, and status codes
from fastapi import APIRouter, Depends, Header, HTTPException, status
# Import SQLAlchemy ORM Session type for type hints and func module for SQL aggregate functions
from sqlalchemy.orm import Session
from sqlalchemy import func

# Import database session dependency generator
from app.db.database import get_db
# Import ORM models for JobStatus enum and JobMetric analytics
from app.models.job import JobStatus
from app.models.job_metric import JobMetric
# Import Pydantic schemas for request validation and response formatting
from app.schemas.job import JobCreate, JobResponse

# Import core job management service layer functions
from app.services.job_service import (
    cancel_job,
    create_job,
    get_job,
    requeue_failed_job,
)

# Import queue service layer function to fetch messages from Dead Letter Queue
from app.services.queue_service import get_dead_letter_jobs


# Create an API Router module with a common prefix and OpenAPI tag documentation grouping
router = APIRouter(
    prefix="/jobs",
    tags=["Jobs"],
)

# Endpoint to handle job creation requests via POST /jobs
@router.post(
    "",
    response_model=JobResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_job_endpoint(
# FastAPI automatically validates the incoming request body against JobCreate Pydantic schema (type and payload).
# If required fields are missing, it responds with a 422 Unprocessable Entity error.
    job_data: JobCreate,
#Uses FastAPI's Dependency Injection system to open a database session via get_db(), inject it into the function,
# and automatically close it when the request completes.
    db: Session = Depends(get_db),
    # Read the Idempotency-Key header from the request; defaults to None if omitted
    idempotency_key: str | None = Header(default=None),
):
    # Enforce mandatory Idempotency-Key header to prevent duplicate execution
    if not idempotency_key:
        raise HTTPException(
            status_code=400,
            detail="Idempotency-Key header is required",
        )

    # Delegate job creation and duplicate checking to the service layer
    job, created = create_job(
        db,
        job_data,
        idempotency_key,
    )

    # Return the created or existing Job ORM object (serialized via JobResponse)
    return job

# Endpoint to fetch aggregated execution metrics via GET /jobs/metrics
@router.get("/metrics")
def get_metrics(
    # Inject database session
    db: Session = Depends(get_db),
):
    # Query database for job metric counts and average execution times grouped by event type
    rows = (
        db.query(
            JobMetric.event,
            func.count(JobMetric.id).label("count"),
            func.avg(JobMetric.duration_ms).label("average_duration_ms"),
        )
        .group_by(JobMetric.event)
        .all()
    )

    # Format database rows into a JSON dictionary response structure
    return {
        row.event: {
            "count": row.count,
            "average_duration_ms": (
                round(float(row.average_duration_ms), 2)
                if row.average_duration_ms is not None
                else None
            ),
        }
        for row in rows
    }


# Endpoint to inspect dead-lettered jobs in the queue via GET /jobs/dlq
@router.get("/dlq")
def get_dlq():
    # Retrieve unprocessable/failed jobs from Redis Dead Letter Queue
    return get_dead_letter_jobs()

# Endpoint to retry and requeue a failed dead-lettered job via POST /jobs/dlq/{job_id}/requeue
@router.post(
    "/dlq/{job_id}/requeue",
    response_model=JobResponse,
)
def requeue_dlq_job(
    job_id: int,
    db: Session = Depends(get_db),
):
    # Attempt to reset job state and re-enqueue via service layer
    job = requeue_failed_job(db, job_id)

    # Return 404 if the job ID does not exist
    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Job not found",
        )

    # Return 409 Conflict if attempting to requeue a job that is not in FAILED state
    if job.status != JobStatus.QUEUED:
        raise HTTPException(
            status_code=409,
            detail="Only failed jobs can be requeued",
        )

    return job

# Endpoint to fetch job details by ID via GET /jobs/{job_id}
@router.get(
    "/{job_id}",
    response_model=JobResponse,
)
def get_job_endpoint(
    job_id: int,
    db: Session = Depends(get_db),
):
    # Fetch job instance from database via service layer
    job = get_job(db, job_id)

    # Return 404 if job does not exist
    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Job not found",
        )
    return job # Returns the SQLAlchemy Job object, which FastAPI formats into JSON based on JobResponse

# Endpoint to cancel an active/queued job via POST /jobs/{job_id}/cancel
@router.post(
    "/{job_id}/cancel",
    response_model=JobResponse,
)
def cancel_job_endpoint(
    job_id: int,
    db: Session = Depends(get_db),
):
    # Attempt to cancel job execution via service layer
    job = cancel_job(db, job_id)

    # Return 404 if job does not exist
    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Job not found",
        )

    return job