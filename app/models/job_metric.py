# Import datetime class for recording timestamp fields
from datetime import datetime

# Import SQLAlchemy column types for mapping database field types
from sqlalchemy import DateTime, Integer, String
# Import SQLAlchemy ORM 2.0 type-hinting mechanisms for declarative mapping
from sqlalchemy.orm import Mapped, mapped_column

# Import declarative Base class from database configuration
from app.db.database import Base


# Define SQLAlchemy ORM model mapped to the "job_metrics" database table for telemetry tracking
class JobMetric(Base):
    # Set target PostgreSQL table name
    __tablename__ = "job_metrics"

    # Primary key identifier column; auto-increments with each inserted metric entry
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    # Identifier referencing the job associated with this telemetry/metric event
    job_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # String field describing the type of metric event recorded (e.g., "job_completed", "job_failed")
    event: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    # Optional integer field storing task processing execution time measured in milliseconds
    duration_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    # Timestamp recording exact UTC date and time when the metric entry was created
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )