"""Small load test that also verifies idempotency under concurrency.

Sends N distinct requests, then replays every Idempotency-Key concurrently and asserts that
each replay returns the ORIGINAL request id (no duplicate work), then prints latency stats.
"""

import asyncio
import os
import statistics
import time
import uuid

import httpx

API_URL = os.environ.get("OPSPILOT_API", "http://localhost:8000") + "/api/v1/requests"
REQUESTS = int(os.environ.get("LOAD_REQUESTS", "50"))
CONCURRENCY = int(os.environ.get("LOAD_CONCURRENCY", "10"))


async def post(client: httpx.AsyncClient, sem: asyncio.Semaphore, key: str, index: int):
    payload = {
        "subject": f"Load test request {index}",
        "body": "Automated load test payload for the account deletion policy.",
        "requester": "load_tester",
        "priority": "low",
    }
    async with sem:
        started = time.perf_counter()
        response = await client.post(API_URL, json=payload, headers={"Idempotency-Key": key})
        return response, (time.perf_counter() - started) * 1000


async def main() -> int:
    keys = [f"load-{uuid.uuid4()}" for _ in range(REQUESTS)]
    sem = asyncio.Semaphore(CONCURRENCY)
    async with httpx.AsyncClient(timeout=30) as client:
        first = await asyncio.gather(*(post(client, sem, k, i) for i, k in enumerate(keys)))
        ids = {}
        failures = 0
        for key, (response, _) in zip(keys, first, strict=True):
            if response.status_code == 202:
                ids[key] = response.json()["request_id"]
            else:
                failures += 1
                print(f"FAILED {response.status_code}: {response.text[:120]}")

        replays = await asyncio.gather(*(post(client, sem, k, i) for i, k in enumerate(keys)))
        duplicates = sum(
            1
            for key, (response, _) in zip(keys, replays, strict=True)
            if key in ids
            and (response.status_code != 200 or response.json()["request_id"] != ids[key])
        )

    latencies = sorted(ms for _, ms in first)
    print(f"requests={REQUESTS} accepted={len(ids)} failed={failures}")
    print(f"idempotent replays creating duplicate work: {duplicates}")
    print(
        f"latency ms: p50={statistics.median(latencies):.0f} "
        f"p95={latencies[int(len(latencies) * 0.95) - 1]:.0f} max={latencies[-1]:.0f}"
    )
    return 1 if failures or duplicates else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
