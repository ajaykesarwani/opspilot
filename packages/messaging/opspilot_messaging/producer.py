import json
import logging
from typing import Protocol

from confluent_kafka import Producer
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class EventPublisher(Protocol):
    def publish(self, topic: str, event: BaseModel) -> None:
        """Publish an event to the specified topic."""
        ...
        
    def flush(self) -> None:
        """Wait for all messages in the Producer queue to be delivered."""
        ...

class KafkaEventPublisher:
    def __init__(self, bootstrap_servers: str):
        self._producer = Producer({
            'bootstrap.servers': bootstrap_servers
        })
        logger.info(f"Initialized KafkaEventPublisher with servers: {bootstrap_servers}")

    def publish(self, topic: str, event: BaseModel) -> None:
        payload = event.model_dump_json()
        key = str(getattr(event, 'request_id', getattr(event, 'event_id', '')))
        self._producer.produce(
            topic, 
            key=key.encode("utf-8"), 
            value=payload.encode("utf-8")
        )
        self._producer.poll(0)

    def flush(self) -> None:
        self._producer.flush()

class InMemoryEventPublisher:
    def __init__(self):
        self.events: list[tuple[str, BaseModel]] = []

    def publish(self, topic: str, event: BaseModel) -> None:
        self.events.append((topic, event))

    def flush(self) -> None:
        pass
