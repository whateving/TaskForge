from sqlalchemy.orm import Session

from app.models.job_metric import JobMetric


def record_metric(
    db: Session,
    job_id: int,
    event: str,
    duration_ms: int | None = None,
) -> None:
    metric = JobMetric(
        job_id=job_id,
        event=event,
        duration_ms=duration_ms,
    )

    try:
        db.add(metric)
        db.commit()

        print(
            f"[METRICS] "
            f"Recorded {event} for job {job_id}"
        )

    except Exception:
        db.rollback()

        print(
            f"[METRICS] "
            f"Failed to record {event} for job {job_id}"
        )

        raise