# Import datetime class for recording execution timestamps
from datetime import datetime

# Import SQLAlchemy column types and ForeignKeys for relational database mappings
from sqlalchemy import DateTime, ForeignKey, Integer
# Import SQLAlchemy ORM 2.0 type-hinting mechanisms for declarative mapping
from sqlalchemy.orm import Mapped, mapped_column

# Import declarative Base class from database configuration
from app.db.database import Base


# Define SQLAlchemy ORM model mapped to the "job_executions" database table
class JobExecution(Base):
    # Set target PostgreSQL table name
    __tablename__ = "job_executions"

    # Primary key identifier column; auto-increments with each inserted row
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    # Foreign key referencing jobs.id; CASCADE deletes execution logs if the parent job is deleted
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True, # That means PostgreSQL will allow only one execution record per job.
    )

    # Timestamp recording exact UTC date and time when the job execution took place
    executed_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )