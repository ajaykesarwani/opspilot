import json
import logging

from fastapi.testclient import TestClient

from opspilot_common.logging import JsonFormatter

VALID = {
    "subject": "Customer escalation",
    "body": "Customer reports a repeated billing error and wants a refund.",
    "requester": "ops.agent",
}


def test_incoming_correlation_id_is_echoed(client: TestClient) -> None:
    response = client.post(
        "/api/v1/requests", json=VALID, headers={"X-Correlation-ID": "trace-abc-12345"}
    )
    assert response.headers["X-Correlation-ID"] == "trace-abc-12345"
    assert response.json()["correlation_id"] == "trace-abc-12345"


def test_invalid_incoming_correlation_id_is_replaced(client: TestClient) -> None:
    response = client.get("/healthz", headers={"X-Correlation-ID": "bad id!"})
    generated = response.headers["X-Correlation-ID"]
    assert generated != "bad id!"
    assert len(generated) == 32


class _CaptureHandler(logging.Handler):
    """Formats records at emit time, while the request's correlation ID is still set."""

    def __init__(self) -> None:
        super().__init__(logging.INFO)
        self.setFormatter(JsonFormatter("opspilot-api"))
        self.lines: list[dict] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(json.loads(self.format(record)))


def test_correlation_id_appears_in_json_logs(client: TestClient) -> None:
    handler = _CaptureHandler()
    logging.getLogger().addHandler(handler)
    try:
        client.post("/api/v1/requests", json=VALID, headers={"X-Correlation-ID": "log-check-12345"})
    finally:
        logging.getLogger().removeHandler(handler)
    for message in ("request_accepted", "request_completed"):
        matching = [line for line in handler.lines if line["message"] == message]
        assert matching, message
        assert all(line["correlation_id"] == "log-check-12345" for line in matching)
