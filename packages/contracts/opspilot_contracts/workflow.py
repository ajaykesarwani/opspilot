"""Workflow states and the allowed transitions between them (pure logic, no I/O)."""

from collections.abc import Mapping
from enum import StrEnum


class WorkflowStatus(StrEnum):
    RECEIVED = "RECEIVED"
    VALIDATED = "VALIDATED"
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    AWAITING_REVIEW = "AWAITING_REVIEW"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    DEAD_LETTERED = "DEAD_LETTERED"


_S = WorkflowStatus

# FAILED = non-retryable failure. DEAD_LETTERED = retries exhausted or unprocessable message.
# PROCESSING -> QUEUED is the retry edge. A reviewer rejection ends as COMPLETED, with the
# decision stored in the result.
ALLOWED_TRANSITIONS: Mapping[WorkflowStatus, frozenset[WorkflowStatus]] = {
    _S.RECEIVED: frozenset({_S.VALIDATED, _S.FAILED}),
    _S.VALIDATED: frozenset({_S.QUEUED, _S.FAILED}),
    _S.QUEUED: frozenset({_S.PROCESSING, _S.FAILED, _S.DEAD_LETTERED}),
    _S.PROCESSING: frozenset({_S.AWAITING_REVIEW, _S.QUEUED, _S.FAILED, _S.DEAD_LETTERED}),
    _S.AWAITING_REVIEW: frozenset({_S.COMPLETED, _S.FAILED}),
    _S.COMPLETED: frozenset(),
    _S.FAILED: frozenset(),
    _S.DEAD_LETTERED: frozenset(),
}

TERMINAL_STATUSES = frozenset(s for s, targets in ALLOWED_TRANSITIONS.items() if not targets)


class InvalidTransitionError(ValueError):
    def __init__(self, current: WorkflowStatus, new: WorkflowStatus) -> None:
        super().__init__(f"Illegal workflow transition {current.value} -> {new.value}")
        self.current = current
        self.new = new


def assert_transition(current: WorkflowStatus, new: WorkflowStatus) -> None:
    if new not in ALLOWED_TRANSITIONS[current]:
        raise InvalidTransitionError(current, new)
