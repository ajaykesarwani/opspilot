from collections import deque

import pytest

from opspilot_contracts import (
    ALLOWED_TRANSITIONS,
    TERMINAL_STATUSES,
    InvalidTransitionError,
    WorkflowStatus,
    assert_transition,
)

S = WorkflowStatus


def test_exactly_the_eight_required_states_exist() -> None:
    assert {s.value for s in WorkflowStatus} == {
        "RECEIVED",
        "VALIDATED",
        "QUEUED",
        "PROCESSING",
        "AWAITING_REVIEW",
        "COMPLETED",
        "FAILED",
        "DEAD_LETTERED",
    }


def test_every_state_has_a_transition_entry() -> None:
    assert set(ALLOWED_TRANSITIONS) == set(WorkflowStatus)


def test_terminal_states() -> None:
    assert {S.COMPLETED, S.FAILED, S.DEAD_LETTERED} == TERMINAL_STATUSES


def test_every_state_is_reachable_from_received() -> None:
    seen, queue = {S.RECEIVED}, deque([S.RECEIVED])
    while queue:
        for nxt in ALLOWED_TRANSITIONS[queue.popleft()]:
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    assert seen == set(WorkflowStatus)


@pytest.mark.parametrize(
    ("current", "new"),
    [
        (S.RECEIVED, S.VALIDATED),
        (S.VALIDATED, S.QUEUED),
        (S.QUEUED, S.PROCESSING),
        (S.PROCESSING, S.QUEUED),  # retry
        (S.PROCESSING, S.AWAITING_REVIEW),
        (S.AWAITING_REVIEW, S.COMPLETED),
        (S.PROCESSING, S.DEAD_LETTERED),
    ],
)
def test_allowed_transitions(current: S, new: S) -> None:
    assert_transition(current, new)


@pytest.mark.parametrize(
    ("current", "new"),
    [
        (S.RECEIVED, S.COMPLETED),  # skipping review
        (S.QUEUED, S.COMPLETED),
        (S.PROCESSING, S.COMPLETED),  # must go through human review
        (S.COMPLETED, S.PROCESSING),
        (S.FAILED, S.QUEUED),
        (S.DEAD_LETTERED, S.QUEUED),
        (S.AWAITING_REVIEW, S.PROCESSING),
    ],
)
def test_forbidden_transitions(current: S, new: S) -> None:
    with pytest.raises(InvalidTransitionError):
        assert_transition(current, new)
