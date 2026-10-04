import logging
from typing import Callable

from confluent_kafka import Consumer, KafkaError

logger = logging.getLogger(__name__)

class KafkaEventConsumer:
    def __init__(self, bootstrap_servers: str, group_id: str, topics: list[str]):
        self._consumer = Consumer({
            'bootstrap.servers': bootstrap_servers,
            'group.id': group_id,
            'auto.offset.reset': 'earliest',
            'enable.auto.commit': False
        })
        self._topics = topics
        self._consumer.subscribe(topics)
        self._running = False
        
    def start(self, handler: Callable[[str, bytes], None]) -> None:
        self._running = True
        logger.info(f"Started consuming topics {self._topics}")
        try:
            while self._running:
                msg = self._consumer.poll(timeout=1.0)
                if msg is None:
                    continue
                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    else:
                        logger.error(f"Kafka error: {msg.error()}")
                        break
                        
                # process msg
                try:
                    handler(msg.topic(), msg.value())
                    # Commit only on success
                    self._consumer.commit(asynchronous=False)
                except Exception as e:
                    logger.exception(f"Error processing message from topic {msg.topic()}: {e}")
                    # A robust implementation would use a DLQ here, but we will leave 
                    # DLQ logic to the handler or a wrapping mechanism.
        finally:
            self._consumer.close()
            
    def stop(self) -> None:
        self._running = False
