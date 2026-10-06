from types import SimpleNamespace

import pytest
from confluent_kafka import KafkaError, KafkaException

from opspilot_messaging import consumer as consumer_module
from opspilot_messaging.consumer import KafkaEventConsumer


class FakeRaw:
    def __init__(self, offset, value=b"v", error=None):
        self._offset, self._value, self._error = offset, value, error

    def error(self):
        return self._error

    def topic(self):
        return "t"

    def partition(self):
        return 0

    def offset(self):
        return self._offset

    def key(self):
        return b"k"

    def value(self):
        return self._value

    def headers(self):
        return [("traceparent", b"00-abc")]


class FakeKafka:
    """Replays a script of messages; records commits and seeks."""

    def __init__(self, script, stop):
        self.script, self.stop = list(script), stop
        self.commits, self.seeks, self.closed = [], [], False

    def subscribe(self, topics):
        pass

    def poll(self, timeout):
        if not self.script:
            self.stop()
            return None
        return self.script.pop(0)

    def commit(self, message, asynchronous):
        self.commits.append(message.offset())

    def seek(self, tp):
        self.seeks.append(tp.offset)

    def close(self):
        self.closed = True


@pytest.fixture
def make(monkeypatch):
    monkeypatch.setattr(consumer_module.time, "sleep", lambda _s: None)

    def build(script):
        c = KafkaEventConsumer.__new__(KafkaEventConsumer)
        fake = FakeKafka(script, c.stop)
        c._consumer, c._topics, c._redelivery_delay, c._running = fake, ["t"], 0, False
        return c, fake

    return build


def test_commits_only_after_successful_handling_and_passes_headers(make):
    c, fake = make([FakeRaw(1), FakeRaw(2)])
    seen = []
    c.start(lambda m: seen.append((m.offset, m.headers)))
    assert fake.commits == [1, 2]
    assert seen[0] == (1, {"traceparent": "00-abc"})
    assert fake.closed


def test_failed_handler_is_not_committed_and_is_redelivered(make):
    c, fake = make([FakeRaw(5)])
    calls = []

    def handler(m):
        calls.append(m.offset)
        raise RuntimeError("db down")

    c.start(handler)
    assert fake.commits == []  # never acknowledged
    assert fake.seeks == [5]  # rewound so the same message is delivered again


def test_fatal_kafka_error_is_raised_not_swallowed(make):
    err = SimpleNamespace(
        code=lambda: KafkaError._ALL_BROKERS_DOWN, fatal=lambda: True, __str__=lambda s: "fatal"
    )
    c, fake = make([FakeRaw(0, error=err)])
    with pytest.raises(KafkaException):
        c.start(lambda m: None)
    assert fake.closed
