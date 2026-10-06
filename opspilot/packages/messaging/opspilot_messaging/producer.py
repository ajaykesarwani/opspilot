import logging
from typing import Protocol

from confluent_kafka import Producer
from confluent_kafka.admin import AdminClient, NewTopic
from opentelemetry import propagate
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class PublishError(Exception):
    """The broker did not acknowledge the message."""


class EventPublisher(Protocol):
    def publish(self, topic: str, event: BaseModel, *, key: str | None = None) -> None:
        """Publish and wait for broker acknowledgement. Raises PublishError on failure."""
        ...

    def flush(self) -> None: ...


def _key_for(event: BaseModel) -> str:
    return str(getattr(event, "request_id", None) or getattr(event, "event_id", ""))


class KafkaEventPublisher:
    def __init__(self, bootstrap_servers: str) -> None:
        self._producer = Producer(
            {
                "bootstrap.servers": bootstrap_servers,
                "enable.idempotence": True,
                "acks": "all",
                "message.timeout.ms": 10_000,
            }
        )

    def publish(self, topic: str, event: BaseModel, *, key: str | None = None) -> None:
        headers: dict[str, str] = {}
        propagate.inject(headers)  # W3C traceparent, so consumers continue the same trace
        errors: list[Exception] = []

        def on_delivery(err, _msg) -> None:
            if err is not None:
                errors.append(PublishError(str(err)))

        self._producer.produce(
            topic,
            key=(key or _key_for(event)).encode(),
            value=event.model_dump_json().encode(),
            headers=[(k, v.encode()) for k, v in headers.items()],
            on_delivery=on_delivery,
        )
        # Synchronous on purpose: the caller must know the event reached the broker before it
        # records the request as QUEUED.
        remaining = self._producer.flush(10)
        if remaining or errors:
            raise errors[0] if errors else PublishError("delivery timed out")

    def flush(self) -> None:
        self._producer.flush(10)


class InMemoryEventPublisher:
    """Test double that records events."""

    def __init__(self) -> None:
        self.events: list[tuple[str, BaseModel]] = []
        self.fail = False

    def publish(self, topic: str, event: BaseModel, *, key: str | None = None) -> None:
        if self.fail:
            raise PublishError("simulated broker failure")
        self.events.append((topic, event))

    def flush(self) -> None:
        pass


def ensure_topics(bootstrap_servers: str, topics: tuple[str, ...], timeout: float = 30.0) -> None:
    """Create topics if missing (a consumer subscribing to a missing topic errors out)."""
    admin = AdminClient({"bootstrap.servers": bootstrap_servers})
    futures = admin.create_topics(
        [NewTopic(t, num_partitions=1, replication_factor=1) for t in topics]
    )
    for topic, future in futures.items():
        try:
            future.result(timeout)
        except Exception as exc:  # already-exists is the normal case on restart
            if "TOPIC_ALREADY_EXISTS" not in str(exc):
                raise
            logger.debug("topic_exists", extra={"topic": topic})
