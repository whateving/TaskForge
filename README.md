# TaskForge

TaskForge is a distributed background job processing system built with Python, FastAPI, PostgreSQL, Redis Streams, and multiple workers.

The project focuses on reliability, fault recovery, concurrency, idempotency, retries, observability, and operational recovery.

## Architecture

```text
                    ┌──────────────┐
                    │   FastAPI    │
                    │     API      │
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
                    │ PostgreSQL   │
                    │   Job State  │
                    └──────────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │    Redis     │
                    │    Streams   │
                    └──────┬───────┘
                           │
                ┌──────────┴──────────┐
                ▼                     ▼
         ┌─────────────┐       ┌─────────────┐
         │   Worker    │       │   Worker    │
         │ Thread Pool │       │ Thread Pool │
         └──────┬──────┘       └──────┬──────┘
                │                     │
                └──────────┬──────────┘
                           ▼
                    ┌──────────────┐
                    │ PostgreSQL   │
                    │ Job Results  │
                    └──────────────┘
```

## Features

### Job API

* Create jobs
* Retrieve job status
* Job cancellation
* Request idempotency using `Idempotency-Key`

### Distributed Workers

* Multiple worker processes
* Configurable per-worker concurrency
* Redis Streams consumer groups
* Independent database sessions for concurrent jobs

### Reliability

* Atomic job claiming
* Crash recovery with Redis `XAUTOCLAIM`
* Worker-level idempotency
* Duplicate side-effect protection
* Retry handling with exponential backoff

### Retry System

Failed jobs are retried using exponential backoff:

```text
attempt 1 → 2 seconds
attempt 2 → 4 seconds
attempt 3 → 8 seconds
```

Retry scheduling uses `next_retry_at` so workers do not block while waiting for the next attempt.

### Dead Letter Queue

Jobs that exhaust their retry attempts are moved to a Redis Dead Letter Queue.

The API provides:

```text
GET  /jobs/dlq
POST /jobs/dlq/{job_id}/requeue
```

This allows failed jobs to be inspected and manually recovered.

### Cancellation

Queued jobs can be cancelled before processing begins:

```text
POST /jobs/{job_id}/cancel
```

### Observability

TaskForge records job events such as:

* processing
* completed
* retry
* failed

Metrics can be viewed through:

```text
GET /jobs/metrics
```

### Load Testing

The worker system was benchmarked using a simulated 3-second workload.

| Configuration        | Total Time |    Throughput |
| -------------------- | ---------: | ------------: |
| 1 worker × 1 thread  |     91.87s | 0.33 jobs/sec |
| 1 worker × 3 threads |     31.03s | 0.97 jobs/sec |
| 1 worker × 6 threads |     15.49s | 1.94 jobs/sec |

The results showed approximately linear scaling for this workload as concurrency increased.

## Tech Stack

* Python
* FastAPI
* PostgreSQL
* SQLAlchemy
* Redis Streams
* Pydantic
* Alembic
* Pytest
* Docker Compose

## Project Structure

```text
TaskForge/
├── app/
│   ├── api/
│   ├── core/
│   ├── db/
│   ├── models/
│   ├── schemas/
│   ├── services/
│   └── workers/
├── alembic/
├── benchmarks/
├── tests/
├── docker-compose.yml
├── requirements.txt
└── README.md
```

## Running Locally

### 1. Start PostgreSQL and Redis

```bash
docker compose up -d
```

### 2. Activate the virtual environment

```bash
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Run database migrations

```bash
alembic upgrade head
```

### 5. Start the API

```bash
python -m uvicorn app.main:app --reload
```

The API will be available at:

```text
http://127.0.0.1:8000
```

Swagger documentation:

```text
http://127.0.0.1:8000/docs
```

### 6. Start a worker

In another terminal:

```bash
python -m app.workers.worker
```

Multiple workers can be started in separate terminals.

## Example Job

Create a job:

```http
POST /jobs
Idempotency-Key: example-123
Content-Type: application/json
```

```json
{
  "type": "example",
  "payload": {}
}
```

The API returns the created job and its current status.

## Failure Recovery

TaskForge is designed to handle several failure scenarios.

### Worker crash

If a worker claims a job and crashes before acknowledging the Redis message, another worker can recover the message after it becomes idle.

### Duplicate execution

A `job_executions` record is used to prevent a completed side effect from being executed twice.

### Retry exhaustion

When a job exceeds its automatic retry limit, it is moved to the Dead Letter Queue for manual inspection and recovery.

## Design Goals

The primary goal of TaskForge was not simply to build a background worker.

The project was designed to explore backend engineering problems around:

* Distributed job processing
* Failure recovery
* Idempotency
* Concurrency
* Retry scheduling
* Queue semantics
* Operational observability
* Performance measurement

## Status

TaskForge is a completed backend engineering project demonstrating a reliable distributed job processing architecture built with Python.

Future improvements could include:

* Transactional outbox
* Priority queues
* More advanced metrics
* Authentication and authorization
* Production deployment
