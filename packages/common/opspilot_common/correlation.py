"""Correlation ID handling via a context variable, so any log line can pick it up."""

import re
import uuid
from contextvars import ContextVar

CORRELATION_ID_HEADER = "X-Correlation-ID"

# Accept only short, log-safe IDs from callers; anything else is replaced.
_VALID_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")

_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def new_correlation_id() -> str:
    return uuid.uuid4().hex


def resolve_correlation_id(incoming: str | None) -> str:
    """Return the caller's ID if well-formed, otherwise a fresh one."""
    if incoming and _VALID_ID.fullmatch(incoming):
        return incoming
    return new_correlation_id()


def set_correlation_id(value: str) -> None:
    _correlation_id.set(value)


def get_correlation_id() -> str | None:
    return _correlation_id.get()
