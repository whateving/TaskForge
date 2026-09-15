from __future__ import annotations

import time
import uuid
from typing import Any

import requests


BASE_URL = "http://127.0.0.1:8000"
JOBS_URL = f"{BASE_URL}/jobs"
REQUEST_TIMEOUT = 10
POLL_INTERVAL = 0.5
CONCURRENT_JOBS = 12


class DemoError(RuntimeError):
    pass


def request(method: str, url: str, **kwargs: Any) -> requests.Response:
    response = requests.request(
        method,
        url,
        timeout=REQUEST_TIMEOUT,
        **kwargs,
    )

    if response.status_code >= 400:
        raise DemoError(
            f"{method} {url} failed: "
            f"{response.status_code} {response.text}"
        )

    return response


def get_health() -> dict:
    return request("GET", f"{BASE_URL}/health").json()


def create_job(
    job_type: str = "demo-job",
    payload: dict | None = None,
    idempotency_key: str | None = None,
) -> tuple[dict, bool]:
    payload = payload or {}
    idempotency_key = idempotency_key or f"demo-{uuid.uuid4().hex}"

    response = request(
        "POST",
        JOBS_URL,
        json={"type": job_type, "payload": payload},
        headers={"Idempotency-Key": idempotency_key},
    )

    return response.json(), response.status_code == 201


def get_job(job_id: int) -> dict:
    return request("GET", f"{JOBS_URL}/{job_id}").json()


def cancel_job(job_id: int) -> dict:
    return request("POST", f"{JOBS_URL}/{job_id}/cancel").json()


def get_metrics() -> dict:
    return request("GET", f"{JOBS_URL}/metrics").json()


def get_dlq() -> list[dict]:
    return request("GET", f"{JOBS_URL}/dlq").json()


def requeue_dlq_job(job_id: int) -> dict:
    return request(
        "POST",
        f"{JOBS_URL}/dlq/{job_id}/requeue",
    ).json()


def wait_for_status(
    job_id: int,
    wanted_statuses: set[str],
    timeout_seconds: float,
) -> dict:
    started = time.perf_counter()

    while True:
        job = get_job(job_id)

        if job["status"] in wanted_statuses:
            return job

        if time.perf_counter() - started >= timeout_seconds:
            raise TimeoutError(
                f"Job {job_id} did not reach {wanted_statuses} "
                f"within {timeout_seconds}s. "
                f"Current status: {job['status']}"
            )

        time.sleep(POLL_INTERVAL)


def print_job(job: dict) -> None:
    print(
        f"job_id={job['id']} "
        f"status={job['status']} "
        f"attempts={job['attempts']} "
        f"max_retries={job['max_retries']}"
    )


def test_health() -> None:
    print("\n" + "=" * 72)
    print("TEST 1: HEALTH")
    print("=" * 72)
    print("Health:", get_health())


def test_idempotency() -> None:
    print("\n" + "=" * 72)
    print("TEST 2: IDEMPOTENCY")
    print("=" * 72)

    key = f"idempotency-demo-{uuid.uuid4().hex}"

    first, created_first = create_job(
        job_type="idempotency-demo",
        idempotency_key=key,
    )

    second, created_second = create_job(
        job_type="idempotency-demo",
        idempotency_key=key,
    )

    print(f"First:  job_id={first['id']} created={created_first}")
    print(f"Second: job_id={second['id']} created={created_second}")

    if first["id"] != second["id"]:
        raise DemoError("Idempotency failed: different job IDs returned.")

    print("PASS")


def test_normal_job() -> None:
    print("\n" + "=" * 72)
    print("TEST 3: NORMAL JOB")
    print("=" * 72)

    job, _ = create_job(
        job_type="normal-demo",
        payload={},
    )

    print("Created:")
    print_job(job)

    result = wait_for_status(
        job["id"],
        {"completed", "failed"},
        timeout_seconds=30,
    )

    print("Final:")
    print_job(result)

    if result["status"] != "completed":
        raise DemoError(f"Expected completed, got {result['status']}")

    print("PASS")


def test_concurrency() -> None:
    print("\n" + "=" * 72)
    print("TEST 4: CONCURRENCY")
    print("=" * 72)
    print("Recommended setup: 2 workers x 3 threads = 6 concurrent jobs.")

    job_ids: list[int] = []
    started = time.perf_counter()

    for index in range(CONCURRENT_JOBS):
        job, _ = create_job(
            job_type="concurrency-demo",
            payload={"index": index},
        )
        job_ids.append(job["id"])

    print(f"Created {len(job_ids)} jobs.")

    while True:
        completed = 0

        for job_id in job_ids:
            if get_job(job_id)["status"] in {"completed", "failed"}:
                completed += 1

        if completed == len(job_ids):
            break

        time.sleep(POLL_INTERVAL)

    elapsed = time.perf_counter() - started
    throughput = len(job_ids) / elapsed

    print(f"Completed:  {completed}/{len(job_ids)}")
    print(f"Total time: {elapsed:.2f}s")
    print(f"Throughput: {throughput:.2f} jobs/sec")

    if completed != len(job_ids):
        raise DemoError("Not all concurrent jobs completed.")

    print("PASS")


def test_cancellation() -> None:
    print("\n" + "=" * 72)
    print("TEST 5: CANCELLATION")
    print("=" * 72)

    job, _ = create_job(
        job_type="cancellation-demo",
        payload={},
    )

    cancelled = cancel_job(job["id"])

    print_job(cancelled)

    if cancelled["status"] != "cancelled":
        raise DemoError(
            f"Expected cancelled, got {cancelled['status']}"
        )

    print("PASS")


def test_retry_and_dlq() -> int:
    print("\n" + "=" * 72)
    print("TEST 6: RETRY + DLQ")
    print("=" * 72)

    job, _ = create_job(
        job_type="retry-demo",
        payload={"should_fail": True},
    )

    print(f"Created failing job {job['id']}.")

    failed = wait_for_status(
        job["id"],
        {"failed"},
        timeout_seconds=60,
    )

    print_job(failed)

    if failed["attempts"] < failed["max_retries"]:
        raise DemoError(
            "Job failed before exhausting the configured retries."
        )

    print("PASS")
    return job["id"]


def test_dlq_requeue(job_id: int) -> None:
    print("\n" + "=" * 72)
    print("TEST 7: DLQ INSPECTION + MANUAL REQUEUE")
    print("=" * 72)

    dlq_jobs = get_dlq()

    matches = [item for item in dlq_jobs if item["job_id"] == job_id]

    if not matches:
        raise DemoError(f"Job {job_id} was not found in the DLQ.")

    print("DLQ entry:")
    print(matches[-1])

    requeued = requeue_dlq_job(job_id)

    print("After requeue:")
    print_job(requeued)

    if requeued["status"] != "queued":
        raise DemoError(
            f"Expected queued after requeue, got {requeued['status']}"
        )

    result = wait_for_status(
        job_id,
        {"completed", "failed"},
        timeout_seconds=45,
    )

    print("After worker picked it up again:")
    print_job(result)

    if result["attempts"] <= requeued["attempts"]:
        raise DemoError("Attempt count did not increase after requeue.")

    print("PASS")


def test_metrics() -> None:
    print("\n" + "=" * 72)
    print("TEST 8: METRICS")
    print("=" * 72)

    metrics = get_metrics()

    for event, values in metrics.items():
        print(
            f"{event}: "
            f"count={values['count']} "
            f"average_duration_ms={values['average_duration_ms']}"
        )

    required = {"processing", "completed", "failed"}
    missing = required - metrics.keys()

    if missing:
        raise DemoError(
            f"Missing expected metrics: {sorted(missing)}"
        )

    print("PASS")






def main() -> None:
    print("#" * 72)
    print("TASKFORGE END-TO-END DEMO")
    print("#" * 72)
    print()
    print("Start first:")
    print("  API:     python -m uvicorn app.main:app --reload")
    print("  Worker1: python -m app.workers.worker")
    print("  Worker2: python -m app.workers.worker")
    print()
    print("Recommended configuration:")
    print("  MAX_CONCURRENT_JOBS = 3")
    print("  2 workers x 3 threads = 6 concurrent jobs")

    test_health()
    test_idempotency()
    test_normal_job()
    test_concurrency()

    dlq_job_id = test_retry_and_dlq()
    test_dlq_requeue(dlq_job_id)

    test_metrics()

    print("\n" + "#" * 72)
    print("ALL AUTOMATED TESTS PASSED")
    print("#" * 72)


if __name__ == "__main__":
    main()
