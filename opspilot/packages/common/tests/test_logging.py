import json
import logging

from opspilot_common.correlation import resolve_correlation_id, set_correlation_id
from opspilot_common.logging import JsonFormatter


def _format(record: logging.LogRecord) -> dict:
    return json.loads(JsonFormatter("test-service").format(record))


def _record(msg: str = "hello", **extra: object) -> logging.LogRecord:
    record = logging.LogRecord("t", logging.INFO, __file__, 1, msg, (), None)
    record.__dict__.update(extra)
    return record


def test_json_output_includes_correlation_id_and_extras() -> None:
    set_correlation_id("abcdef123456")
    out = _format(_record(request_id="r-1"))
    assert out["message"] == "hello"
    assert out["service"] == "test-service"
    assert out["level"] == "INFO"
    assert out["correlation_id"] == "abcdef123456"
    assert out["request_id"] == "r-1"


def test_resolve_correlation_id_accepts_valid_and_replaces_invalid() -> None:
    assert resolve_correlation_id("valid-id-123") == "valid-id-123"
    for bad in (None, "", "short", "has spaces in it!", "x" * 65):
        generated = resolve_correlation_id(bad)
        assert generated != bad
        assert len(generated) == 32
