# Import datetime class for managing timestamp fields
from datetime import datetime
# Import standard Python Enum for defining string-based status enumeration values
from enum import Enum

# Import SQLAlchemy column types for mapping database field types
from sqlalchemy import DateTime, Enum as SQLEnum, Integer, JSON, String
# Import SQLAlchemy ORM 2.0 type-hinting mechanisms for declarative mapping
from sqlalchemy.orm import Mapped, mapped_column

# Import declarative Base class from database configuration
from app.db.database import Base


# Define string enumeration class representing allowed lifecycle states of a background job
class JobStatus(str, Enum):
    QUEUED = "queued"          # Task is waiting in queue to be picked up
    PROCESSING = "processing"  # Task is actively being executed by a worker
    COMPLETED = "completed"    # Task finished execution successfully
    FAILED = "failed"          # Task reached max retries and failed permanently
    CANCELLED = "cancelled"    # Task was manually revoked/cancelled by user


# Define SQLAlchemy ORM model mapped to the "jobs" database table
class Job(Base):
    # Set target PostgreSQL table name
    __tablename__ = "jobs"

    # Primary key identifier column; auto-increments with each inserted row
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    # String field identifying the task type or worker handler to run (e.g., "send_email")
    type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    # JSON column holding parameters and input arguments required for job execution
    payload: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
    )

    # State column using the JobStatus enum; defaults to QUEUED upon record creation
    status: Mapped[JobStatus] = mapped_column(
        SQLEnum(JobStatus),
        default=JobStatus.QUEUED,
        nullable=False,
    )

    # Integer counter tracking the number of execution attempts made so far
    attempts: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    # Maximum number of retry attempts permitted before marking job as permanently FAILED
    max_retries: Mapped[int] = mapped_column(
        Integer,
        default=3,
        nullable=False,
    )

    # Optional text column storing stack traces or error messages from failed attempts
    last_error: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )

    # Optional timestamp used by scheduler loops to schedule delayed exponential backoff retries
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    # Unique string header key ensuring identical requests do not result in duplicate jobs
    idempotency_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
    )

    # Timestamp recording exact UTC date and time when the job was initially created
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )