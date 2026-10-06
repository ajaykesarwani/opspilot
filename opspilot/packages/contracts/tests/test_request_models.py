import pytest
from pydantic import ValidationError

from opspilot_contracts import DISCLAIMER, OperationalRequestCreate, Priority

VALID = {
    "subject": "Escalation",
    "body": "Customer reports a repeated billing error.",
    "requester": "ops",
}


def test_defaults_and_whitespace_stripping() -> None:
    model = OperationalRequestCreate(**{**VALID, "subject": "  Escalation  "})
    assert model.subject == "Escalation"
    assert model.priority is Priority.NORMAL


def test_extra_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        OperationalRequestCreate(**VALID, unexpected="x")


def test_whitespace_only_subject_rejected() -> None:
    with pytest.raises(ValidationError):
        OperationalRequestCreate(**{**VALID, "subject": "     "})


def test_disclaimer_states_recommendations_only() -> None:
    assert "recommendations only" in DISCLAIMER
