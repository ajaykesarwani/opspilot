"""API -> event -> worker -> API, with in-memory infrastructure but the real code paths."""

from pathlib import Path

from opspilot_contracts import Topics
from opspilot_messaging import Message
from opspilot_orchestration import create_workflow
from opspilot_rag import MockEmbedder, VectorStore, load_knowledge_base
from opspilot_worker.main import WorkerService
from opspilot_worker.settings import Settings as WorkerSettings

KB = Path(__file__).parents[3] / "data" / "knowledge_base"


def test_request_flows_through_worker_to_human_approval(client, repository, publisher):
    created = client.post(
        "/api/v1/requests",
        json={
            "subject": "Account question",
            "body": "How long does account deletion take?",
            "requester": "ops.agent",
        },
    )
    assert created.status_code == 202
    request_id = created.json()["request_id"]

    store = VectorStore(MockEmbedder())
    load_knowledge_base(store, KB)
    worker = WorkerService(
        WorkerSettings(_env_file=None), repository, publisher, create_workflow(store)
    )
    [(topic, event)] = [e for e in publisher.events if e[0] == Topics().requested]
    worker.handle_message(Message(topic, 0, 0, b"k", event.model_dump_json().encode()))

    detail = client.get(f"/api/v1/requests/{request_id}").json()
    assert detail["status"] == "AWAITING_REVIEW"
    assert detail["result"]["recommendation"]["citations"] == ["policies.md"]

    approved = client.post(f"/api/v1/requests/{request_id}/approve")
    assert approved.json()["status"] == "COMPLETED"
    assert client.get(f"/api/v1/requests/{request_id}").json()["status"] == "COMPLETED"

    from uuid import UUID

    trail = [(a.to_status.value, a.actor) for a in repository.audit_trail(UUID(request_id))]
    assert trail == [
        ("RECEIVED", "ops.agent"),
        ("VALIDATED", "api"),
        ("QUEUED", "api"),
        ("PROCESSING", "worker"),
        ("AWAITING_REVIEW", "worker"),
        ("COMPLETED", "human_reviewer"),
    ]
