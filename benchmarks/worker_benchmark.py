import statistics
import time
import uuid

import requests


API_URL = "http://127.0.0.1:8000/jobs"

TOTAL_JOBS = 30
POLL_INTERVAL = 0.25
TIMEOUT_SECONDS = 180


def create_jobs() -> list[int]:
    job_ids = []

    print(f"\nCreating {TOTAL_JOBS} jobs...")

    for index in range(TOTAL_JOBS):
        response = requests.post(
            API_URL,
            json={
                "type": "benchmark-job",
                "payload": {},
            },
            headers={
                "Idempotency-Key": (
                    f"benchmark-{uuid.uuid4().hex}"
                ),
            },
            timeout=10,
        )

        response.raise_for_status()

        job_id = response.json()["id"]
        job_ids.append(job_id)

    print(f"Created jobs: {job_ids}")

    return job_ids


def wait_for_completion(job_ids: list[int]) -> tuple[float, list[float]]:
    start_time = time.perf_counter()

    completion_times = {}

    while len(completion_times) < len(job_ids):

        elapsed = time.perf_counter() - start_time

        if elapsed > TIMEOUT_SECONDS:
            raise TimeoutError(
                "Benchmark timed out before all jobs completed."
            )

        for job_id in job_ids:

            if job_id in completion_times:
                continue

            response = requests.get(
                f"{API_URL}/{job_id}",
                timeout=10,
            )

            response.raise_for_status()

            job = response.json()

            if job["status"] in {"completed", "failed"}:
                completion_times[job_id] = (
                    time.perf_counter() - start_time
                )

        time.sleep(POLL_INTERVAL)

    total_time = time.perf_counter() - start_time

    latencies = list(completion_times.values())

    return total_time, latencies


def run_benchmark() -> None:
    print("=" * 50)
    print("TaskForge Load Test")
    print("=" * 50)

    job_ids = create_jobs()

    print("\nWaiting for jobs to finish...")

    total_time, latencies = wait_for_completion(job_ids)

    throughput = TOTAL_JOBS / total_time

    print("\n" + "=" * 50)
    print("Results")
    print("=" * 50)

    print(f"Jobs:              {TOTAL_JOBS}")
    print(f"Total time:        {total_time:.2f} seconds")
    print(f"Throughput:        {throughput:.2f} jobs/sec")
    print(f"Average latency:   {statistics.mean(latencies):.2f} sec")
    print(f"Median latency:    {statistics.median(latencies):.2f} sec")
    print(f"P95 latency:       {statistics.quantiles(latencies, n=20)[18]:.2f} sec")
    print(f"Min latency:       {min(latencies):.2f} sec")
    print(f"Max latency:       {max(latencies):.2f} sec")


if __name__ == "__main__":
    run_benchmark()