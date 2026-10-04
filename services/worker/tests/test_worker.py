import json
import logging
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from opspilot_contracts import WorkflowStatus
from opspilot_contracts.events import WorkflowRequestedEvent, WorkflowRequestedPayload, Priority
from opspilot_worker.main import WorkerService
from opspilot_worker.settings import Settings


@pytest.fixture
def mock_repository():
    return MagicMock()

@pytest.fixture
def worker(mock_repository):
    settings = Settings(mock_mode=True)
    svc = WorkerService(settings)
    svc.repository = mock_repository
    return svc

def test_successful_processing(worker, mock_repository):
    event_id = uuid4()
    request_id = uuid4()
    
    event = WorkflowRequestedEvent(
        event_id=event_id,
        request_id=request_id,
        correlation_id="test-corr",
        payload=WorkflowRequestedPayload(priority=Priority.HIGH)
    )
    
    value = event.model_dump_json().encode("utf-8")
    
    worker.handle_message("workflow.requested", value)
    
    assert mock_repository.transition.call_count == 2
    
    call_1 = mock_repository.transition.call_args_list[0]
    assert call_1.kwargs["request_id"] == request_id
    assert call_1.kwargs["new_status"] == WorkflowStatus.PROCESSING
    
    call_2 = mock_repository.transition.call_args_list[1]
    assert call_2.kwargs["request_id"] == request_id
    assert call_2.kwargs["new_status"] == WorkflowStatus.AWAITING_REVIEW
