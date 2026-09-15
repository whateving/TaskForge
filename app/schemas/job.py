# Import datetime class for validating timestamp response fields
from datetime import datetime

# Import BaseModel and ConfigDict from Pydantic for data validation and serialization settings
from pydantic import BaseModel, ConfigDict

# Import JobStatus enum to type-hint the job lifecycle state in API responses
from app.models.job import JobStatus


# Schema defining expected request payload structure when creating a new job via POST requests
class JobCreate(BaseModel):
    type: str       # Name or identifier of task type to run (e.g., "send_email")
    payload: dict    # Arbitrary dictionary containing parameters required for execution


# Schema defining structure of job data returned to API clients in HTTP responses
class JobResponse(BaseModel):
    id: int                     # Unique auto-incremented database ID assigned to the job
    type: str                   # Task type identifier
    payload: dict               # Task parameters dictionary
    status: JobStatus           # Current state of the job (e.g., QUEUED, PROCESSING, COMPLETED)
    attempts: int               # Count of execution attempts made by workers
    max_retries: int            # Maximum allowed retries before marking as permanently failed
    last_error: str | None      # Error message/stack trace from the most recent failed execution
    idempotency_key: str        # Unique key used to prevent duplicate request processing
    created_at: datetime        # UTC timestamp indicating when job record was inserted

    # Configure model to automatically extract values from ORM/SQLAlchemy model instances (formerly orb_mode=True)
    model_config = ConfigDict(from_attributes=True)