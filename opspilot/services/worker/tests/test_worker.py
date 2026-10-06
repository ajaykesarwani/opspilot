from pathlib import Path
from uuid import UUID, uuid4

import pytest

from opspilot_contracts import (
    DeadLetterEvent,
    DeadLetterReason,
    OperationalRequestCreate,
    Topics,
    WorkflowFailedEvent,
    WorkflowRequestedEvent,
    WorkflowRequestedPayload,
    WorkflowStatus,
)
from opspilot_messaging import InMemoryEventPublisher, Message, PublishError
from opspilot_orchestration import MockLLMProvider, create_workflow
from opspilot_persistence.repositories.base import NewRequest
from opspilot_persistence.repositories.memory import InMemoryRequestRepository
from opspilot_rag import MockEmbedder, VectorStore, load_knowledge_base
from opspilot_worker.main import WorkerService
from opspilot_worker.settings import Settings

KB = Path(__file__).parents[3] / "data" / "knowledge_base"
TOPICS = Topics()
CORR = "corr-12345678"


class CountingLLM(MockLLMProvider):
    def __init__(self, fail_times: int = 0):
        self.calls = 0
        self.fail_times = fail_times

    def generate_structured(self, prompt, schema):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("provider exploded")
        return super().generate_structured(prompt, schema)


class Env:
    def __init__(self, llm=None, workflow=None):
        self.repo = InMemoryRequestRepository()
        self.pub = InMemoryEventPublisher()
        self.llm = llm or CountingLLM()
        store = VectorStore(MockEmbedder())
        load_knowledge_base(store, KB)
        self.sleeps: list[float] = []
        self.svc = WorkerService(
            Settings(_env_file=None, max_attempts=3, queued_wait_polls=3),
            self.repo,
            self.pub,
            workflow or create_workflow(store, self.llm),
            sleep=self.sleeps.append,
        )

    def queued_request(self, body="How long does account deletion take?") -> UUID:
        rid = uuid4()
        self.repo.create_or_get(
            NewRequest(
                request_id=rid,
                correlation_id=CORR,
                idempotency_key=f"key-{rid}",
                fingerprint="f",
                payload=OperationalRequestCreate(
                    subject="Quick question", body=body, requester="tester"
                ),
            )
        )
        self.repo.transition(rid, WorkflowStatus.QUEUED, actor="api", correlation_id=CORR)
        return rid

    def deliver(self, rid: UUID, offset: int = 7) -> None:
        event = WorkflowRequestedEvent(
            request_id=rid, correlation_id=CORR, payload=WorkflowRequestedPayload(priority="low")
        )
        self.raw(event.model_dump_json().encode(), offset)

    def raw(self, value: bytes, offset: int = 7) -> None:
        self.svc.handle_message(Message(TOPICS.requested, 0, offset, b"k", value))

    def topics(self, topic: str):
        return [e for t, e in self.pub.events if t == topic]


@pytest.fixture
def env() -> Env:
    return Env()


def test_success_stores_result_and_awaits_human_review(env):
    rid = env.queued_request()
    env.deliver(rid)
    record = env.repo.get(rid)
    assert record.status == WorkflowStatus.AWAITING_REVIEW  # never auto-completed
    assert record.result["recommendation"]["citations"] == ["policies.md"]
    assert record.result["insufficient_evidence"] is False
    assert len(env.topics(TOPICS.completed)) == 1
    assert env.topics(TOPICS.dlq) == []


def test_unanswerable_request_stores_abstention(env):
    rid = env.queued_request("What is the capital of France?")
    env.deliver(rid)
    result = env.repo.get(rid).result
    assert result["insufficient_evidence"] is True
    assert result["recommendation"]["confidence_category"] == "insufficient_evidence"


def test_duplicate_delivery_is_idempotent(env):
    rid = env.queued_request()
    env.deliver(rid)
    env.deliver(rid)
    assert env.llm.calls == 1
    assert len(env.topics(TOPICS.completed)) == 1
    assert env.repo.get(rid).status == WorkflowStatus.AWAITING_REVIEW


def test_malformed_message_is_dead_lettered(env):
    env.raw(b"{not json", offset=42)
    [dlq] = env.topics(TOPICS.dlq)
    assert isinstance(dlq, DeadLetterEvent)
    assert dlq.payload.reason == DeadLetterReason.MALFORMED_MESSAGE
    assert dlq.payload.source_offset == 42
    assert dlq.payload.original_message == "{not json"


def test_unknown_request_is_dead_lettered(env):
    env.deliver(uuid4())
    [dlq] = env.topics(TOPICS.dlq)
    assert dlq.payload.reason == DeadLetterReason.REQUEST_NOT_FOUND


def test_transient_failure_is_retried_with_backoff():
    env = Env(llm=CountingLLM(fail_times=0))

    class FlakyWorkflow:
        def __init__(self, inner):
            self.inner, self.n = inner, 0

        def invoke(self, state):
            self.n += 1
            if self.n == 1:
                raise RuntimeError("transient")
            return self.inner.invoke(state)

    env.svc.workflow = FlakyWorkflow(env.svc.workflow)
    rid = env.queued_request()
    env.deliver(rid)
    record = env.repo.get(rid)
    assert record.status == WorkflowStatus.AWAITING_REVIEW
    assert record.retry_count == 1
    assert env.sleeps == [1.0]


def test_retries_exhausted_dead_letters_request():
    class AlwaysFails:
        def invoke(self, state):
            raise RuntimeError("down")

    env = Env(workflow=AlwaysFails())
    rid = env.queued_request()
    env.deliver(rid)
    record = env.repo.get(rid)
    assert record.status == WorkflowStatus.DEAD_LETTERED
    assert record.error_code == "RETRIES_EXHAUSTED"
    assert record.retry_count == 2
    assert env.sleeps == [1.0, 2.0]  # exponential backoff
    [dlq] = env.topics(TOPICS.dlq)
    assert dlq.request_id == rid
    assert dlq.payload.reason == DeadLetterReason.RETRIES_EXHAUSTED


def test_graph_level_failure_marks_request_failed():
    env = Env(llm=CountingLLM(fail_times=99))
    rid = env.queued_request()
    env.deliver(rid)
    record = env.repo.get(rid)
    assert record.status == WorkflowStatus.FAILED
    assert record.error_code == "WORKFLOW_FAILED"
    [failed] = env.topics(TOPICS.failed)
    assert isinstance(failed, WorkflowFailedEvent)


def test_crash_recovery_resumes_from_processing(env):
    rid = env.queued_request()
    env.repo.transition(rid, WorkflowStatus.PROCESSING, actor="worker", correlation_id=CORR)
    env.deliver(rid)  # redelivered after the previous worker died mid-flight
    record = env.repo.get(rid)
    assert record.status == WorkflowStatus.AWAITING_REVIEW
    assert record.retry_count == 1


def test_event_that_never_gets_queued_is_dead_lettered_after_waiting():
    env = Env()
    rid = uuid4()
    env.repo.create_or_get(
        NewRequest(
            rid,
            CORR,
            "key-never-queued",
            "f",
            OperationalRequestCreate(
                subject="Quick question", body="long enough body", requester="t"
            ),
        )
    )
    env.deliver(rid)
    assert len(env.sleeps) == 3  # bounded wait, then give up
    [dlq] = env.topics(TOPICS.dlq)
    assert dlq.payload.reason == DeadLetterReason.INVALID_STATE


def test_failed_dlq_publish_propagates_so_message_is_redelivered(env):
    env.pub.fail = True
    with pytest.raises(PublishError):
        env.raw(b"garbage")


def test_notification_failure_does_not_undo_completed_work(env):
    rid = env.queued_request()
    env.pub.fail = True
    env.deliver(rid)  # completed-event publish fails but must not raise or reprocess
    assert env.repo.get(rid).status == WorkflowStatus.AWAITING_REVIEW
