import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from confluent_kafka import Consumer, KafkaError, KafkaException, TopicPartition

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Message:
    topic: str
    partition: int
    offset: int
    key: bytes | None
    value: bytes
    headers: dict[str, str] = field(default_factory=dict)


class KafkaEventConsumer:
    """At-least-once consumer.

    The offset is committed only after the handler returns. If the handler raises, the offset is
    NOT committed and the consumer seeks back so the same message is redelivered after a short
    delay (instead of being skipped). Handlers must therefore be idempotent, and should handle
    poison messages themselves (e.g. dead-letter them) and return normally.
    """

    def __init__(
        self,
        bootstrap_servers: str,
        group_id: str,
        topics: list[str],
        redelivery_delay: float = 2.0,
    ) -> None:
        self._consumer = Consumer(
            {
                "bootstrap.servers": bootstrap_servers,
                "group.id": group_id,
                "auto.offset.reset": "earliest",
                "enable.auto.commit": False,
            }
        )
        self._topics = topics
        self._redelivery_delay = redelivery_delay
        self._running = False
        self._consumer.subscribe(topics)

    def start(self, handler: Callable[[Message], None]) -> None:
        self._running = True
        logger.info("consumer_started", extra={"topics": self._topics})
        try:
            while self._running:
                raw = self._consumer.poll(timeout=1.0)
                if raw is None:
                    continue
                if raw.error():
                    if raw.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    if raw.error().fatal():
                        raise KafkaException(raw.error())
                    logger.warning("kafka_error", extra={"error": str(raw.error())})
                    continue

                message = Message(
                    topic=raw.topic(),
                    partition=raw.partition(),
                    offset=raw.offset(),
                    key=raw.key(),
                    value=raw.value() or b"",
                    headers={k: v.decode() for k, v in (raw.headers() or []) if v is not None},
                )
                try:
                    handler(message)
                except Exception:
                    logger.exception(
                        "handler_failed_will_redeliver",
                        extra={"topic": message.topic, "offset": message.offset},
                    )
                    self._consumer.seek(
                        TopicPartition(message.topic, message.partition, message.offset)
                    )
                    time.sleep(self._redelivery_delay)
                    continue
                self._consumer.commit(message=raw, asynchronous=False)
        finally:
            self._consumer.close()
            logger.info("consumer_stopped")

    def stop(self) -> None:
        self._running = False
