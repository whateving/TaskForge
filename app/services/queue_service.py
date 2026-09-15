# Import redis-py client library for interacting with Redis Streams
import redis

# Import global settings for Redis connection URL configuration
from app.core.config import settings


# Redis Stream key used for primary background job queuing
STREAM_NAME = "taskforge:jobs"
# Redis Stream key used as Dead Letter Queue (DLQ) for failed/poison pill jobs
DLQ_STREAM_NAME = "taskforge:jobs:dlq"
# Consumer group name shared across all task processing workers
GROUP_NAME = "taskforge-workers"

# A job that has been pending for this long is considered stale.
# Our simulated jobs take 3 seconds, so 10 seconds gives us
# plenty of room while still making local recovery easy to test.
RECOVERY_IDLE_TIME_MS = 10_000


# Initialize Redis client connection using settings URL with automatic response string decoding
redis_client = redis.Redis.from_url(
    settings.redis_url,
    decode_responses=True,
    socket_timeout=10,
)


# Helper function to push permanently failed or exhausted jobs to the Dead Letter Queue stream
def move_to_dead_letter_queue(
    job_id: int,
    attempts: int,
    last_error: str | None,
    original_message_id: str,
) -> None:
    # Append message payload dictionary to the DLQ stream
    redis_client.xadd(
        DLQ_STREAM_NAME,
        {
            "job_id": str(job_id),
            "attempts": str(attempts),
            "last_error": last_error or "",
            "original_message_id": original_message_id,
        },
    )

# Function to initialize the worker consumer group if it does not already exist
def ensure_consumer_group() -> None:
    try:
        # Create consumer group starting from message ID '0' (beginning of stream)
        # mkstream=True automatically creates the stream if it does not exist yet
        redis_client.xgroup_create(
            name=STREAM_NAME,
            groupname=GROUP_NAME,
            id="0",
            mkstream=True,
        )
    except redis.exceptions.ResponseError as exc:
        # Ignore error if consumer group already exists (BUSYGROUP), otherwise raise exception
        if "BUSYGROUP" not in str(exc):
            raise


# Enqueues a job by adding its job_id field to the primary Redis stream
def enqueue_job(job_id: int) -> None:
    redis_client.xadd(
        STREAM_NAME,
        {
            "job_id": str(job_id),
        },
    )


# Dequeues next job for worker processing, prioritizing pending stale messages from crashed workers
def dequeue_job(
    consumer_name: str,
) -> tuple[str, int, bool] | None:
    """
    Return:

        message_id
        job_id
        recovered

    recovered=True means the message was previously delivered
    to another worker and has now been reclaimed.
    """

    # First, try to recover stale jobs from dead workers.
    # Reclaims ownership of pending messages idle for longer than RECOVERY_IDLE_TIME_MS
    result = redis_client.xautoclaim(
        name=STREAM_NAME,
        groupname=GROUP_NAME,
        consumername=consumer_name,
        min_idle_time=RECOVERY_IDLE_TIME_MS,
        start_id="0-0",
        count=1,
    )

    _, messages, _ = result

    # If a stale message was reclaimed, return its info immediately with recovered=True flag
    if messages:
        message_id, fields = messages[0]

        return (
            message_id,
            int(fields["job_id"]),
            True,
        )

    # Otherwise wait for a brand-new job.
    try:
        # Listen for new undelivered messages (">") assigned to this consumer group instance
        # Blocks up to 5000ms (5s) waiting for a new message before timing out
        messages = redis_client.xreadgroup(
            groupname=GROUP_NAME,
            consumername=consumer_name,
            streams={
                STREAM_NAME: ">",
            },
            count=1,
            block=5000,
        )
    except redis.exceptions.TimeoutError:
        # Return None if read times out with no message
        return None

    # Return None if stream is empty
    if not messages:
        return None

    _, stream_messages = messages[0]

    message_id, fields = stream_messages[0]

    # Return message details with recovered=False flag indicating new task
    return (
        message_id,
        int(fields["job_id"]),
        False,
    )

# Retrieves up to 'limit' messages currently sitting in the Dead Letter Queue stream
def get_dead_letter_jobs(
    limit: int = 100,
) -> list[dict]:
    # Query messages directly from the DLQ stream range
    messages = redis_client.xrange(
        DLQ_STREAM_NAME,
        count=limit,
    )

    jobs = []

    # Parse raw string fields returned from Redis into structured dictionaries
    for message_id, fields in messages:
        jobs.append(
            {
                "message_id": message_id,
                "job_id": int(fields["job_id"]),
                "attempts": int(fields["attempts"]),
                "last_error": fields["last_error"] or None,
                "original_message_id": fields["original_message_id"],
            }
        )

    return jobs


# Re-enqueues a job back into the primary task stream for processing
def requeue_dead_letter_job(
    job_id: int,
) -> None:
    enqueue_job(job_id)

# Acknowledges message completion in Redis Stream, removing it from consumer group Pending Entries List (PEL)
def acknowledge_job(message_id: str) -> None:
    redis_client.xack(
        STREAM_NAME,
        GROUP_NAME,
        message_id,
    )