"""Interactive demo against a running stack (`make up`). Three scenarios:

1. an answerable request -> recommendation with citations -> human approval
2. an unanswerable request -> the system abstains instead of guessing
3. a malformed Kafka message -> dead-letter queue (needs the host Kafka listener, port 29092)
"""

import json
import os
import time
import uuid

import httpx

API = os.environ.get("OPSPILOT_API", "http://localhost:8000")
KAFKA = os.environ.get("OPSPILOT_KAFKA", "localhost:29092")
SETTLED = {"AWAITING_REVIEW", "COMPLETED", "FAILED", "DEAD_LETTERED"}


def submit_and_wait(subject: str, body: str, timeout: float = 30.0) -> dict:
    headers = {"Idempotency-Key": f"demo-{uuid.uuid4()}"}
    payload = {"subject": subject, "body": body, "requester": "demo_user", "priority": "normal"}
    created = httpx.post(f"{API}/api/v1/requests", json=payload, headers=headers)
    created.raise_for_status()
    request_id = created.json()["request_id"]
    print(f"[->] {subject!r} accepted as {request_id}")

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        detail = httpx.get(f"{API}/api/v1/requests/{request_id}").json()
        if detail["status"] in SETTLED:
            print(f"[<-] status: {detail['status']}")
            return detail
        time.sleep(0.5)
    raise TimeoutError(f"{request_id} did not settle within {timeout}s (is the worker running?)")


def scenario_answerable() -> None:
    print("\n=== 1. Answerable request, human approval ===")
    detail = submit_and_wait("Account question", "How long does account deletion take?")
    rec = (detail["result"] or {}).get("recommendation", {})
    print(f"    confidence={rec.get('confidence_category')} sources={rec.get('citations')}")
    if detail["status"] == "AWAITING_REVIEW":
        approved = httpx.post(f"{API}/api/v1/requests/{detail['request_id']}/approve")
        print(f"[->] approved: {approved.json()['status']}")


def scenario_abstention() -> None:
    print("\n=== 2. Unanswerable request -> abstention ===")
    detail = submit_and_wait("Quick question", "What is the capital of France?")
    result = detail["result"] or {}
    print(f"    insufficient_evidence={result.get('insufficient_evidence')}")


def scenario_dead_letter() -> None:
    print("\n=== 3. Malformed message -> dead-letter queue ===")
    from confluent_kafka import Consumer, Producer

    marker = f"not-json-{uuid.uuid4().hex[:8]}"
    producer = Producer({"bootstrap.servers": KAFKA})
    producer.produce("workflow.requested", marker.encode())
    producer.flush(10)
    print(f"[->] produced garbage message {marker!r} to workflow.requested")

    consumer = Consumer(
        {
            "bootstrap.servers": KAFKA,
            "group.id": f"demo-{uuid.uuid4().hex[:8]}",
            "auto.offset.reset": "earliest",
        }
    )
    consumer.subscribe(["workflow.dlq"])
    deadline = time.monotonic() + 30
    try:
        while time.monotonic() < deadline:
            msg = consumer.poll(1.0)
            if msg is None or msg.error():
                continue
            event = json.loads(msg.value())
            if event["payload"].get("original_message") == marker:
                print(f"[<-] dead-lettered: reason={event['payload']['reason']}")
                return
        print("[!] no matching DLQ event within 30s (is the worker running?)")
    finally:
        consumer.close()


if __name__ == "__main__":
    scenario_answerable()
    scenario_abstention()
    scenario_dead_letter()
    print("\nDone. Traces: http://localhost:16686  Metrics: http://localhost:9090")
