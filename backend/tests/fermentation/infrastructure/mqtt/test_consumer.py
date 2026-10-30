import asyncio
import logging
from collections.abc import AsyncIterator
from types import SimpleNamespace, TracebackType
from typing import Any

import aiomqtt
import pytest
from sqlalchemy.exc import DBAPIError, IntegrityError, InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from fermon.fermentation.application import IngestReading
from fermon.fermentation.domain import Reading
from fermon.fermentation.infrastructure.mqtt import consumer
from fermon.shared.config import Settings
from tests.fermentation.fakes import InMemoryReadingRepository
from tests.fermentation.infrastructure.mqtt.test_handle_message import TOPIC, payload


def make_settings() -> Settings:
    # Pin every field the consumer reads so ambient env variables cannot change the scripts.
    return Settings(
        mqtt_host="broker",
        mqtt_port=1883,
        mqtt_client_id="test-ingestor",
        mqtt_topic_prefix="fermon",
        mqtt_clean_session=False,
    )


def message(body: bytes, topic: str = TOPIC) -> Any:
    return SimpleNamespace(topic=topic, payload=body)


class FakeClient:
    """Scripted client. outcome: 'fail' (connect error), 'drop' (error mid-stream), 'ok'."""

    def __init__(self, outcome: str, messages: list[Any], stop: asyncio.Event | None) -> None:
        self.outcome = outcome
        self.script = messages
        self.stop = stop
        self.subscriptions: list[tuple[str, int]] = []

    async def __aenter__(self) -> "FakeClient":
        if self.outcome == "fail":
            raise aiomqtt.MqttError("connect refused")
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    async def subscribe(self, topic: str, qos: int = 0) -> None:
        self.subscriptions.append((topic, qos))

    @property
    def messages(self) -> AsyncIterator[Any]:
        return self._stream()

    async def _stream(self) -> AsyncIterator[Any]:
        for item in self.script:
            await asyncio.sleep(0)
            yield item
        if self.outcome == "drop":
            raise aiomqtt.MqttError("connection lost")
        if self.stop is not None:
            self.stop.set()
        await asyncio.Event().wait()  # block like a quiet broker until cancelled


async def run_script(
    outcomes: list[str],
    messages: list[Any] | None = None,
    repo: InMemoryReadingRepository | None = None,
) -> tuple[list[float], list[FakeClient]]:
    """Run the consumer through scripted outcomes; return requested waits and used clients."""
    stop = asyncio.Event()
    waits: list[float] = []
    clients: list[FakeClient] = []
    script = iter(outcomes)

    def factory(settings: Settings) -> FakeClient:
        try:
            client = FakeClient(next(script), messages or [], None)
        except StopIteration:
            stop.set()
            client = FakeClient("ok_idle", [], None)
        clients.append(client)
        return client

    async def fake_wait(_stop: asyncio.Event, seconds: float) -> None:
        waits.append(seconds)
        await asyncio.sleep(0)  # yield so wait_for can interrupt a runaway loop

    ingest = IngestReading(repo or InMemoryReadingRepository())
    await asyncio.wait_for(
        consumer.run_consumer(
            make_settings(), ingest, stop, client_factory=factory, wait=fake_wait
        ),
        timeout=5,
    )
    return waits, clients


async def test_backoff_doubles_and_caps_at_thirty_seconds() -> None:
    waits, _ = await run_script(["fail"] * 8)
    assert waits == [1, 2, 4, 8, 16, 30, 30, 30]


async def test_backoff_resets_after_successful_connect() -> None:
    waits, _ = await run_script(["fail", "fail", "fail", "drop", "fail"])
    assert waits == [1, 2, 4, 1, 2]


async def test_subscribes_with_qos_1_to_configured_topic() -> None:
    _, clients = await run_script(["drop"])
    assert clients[0].subscriptions == [("fermon/tanks/+/readings", 1)]


async def test_stop_during_backoff_exits_promptly() -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    loop.call_later(0.05, stop.set)
    start = loop.time()
    await asyncio.wait_for(
        consumer.run_consumer(
            make_settings(),
            IngestReading(InMemoryReadingRepository()),
            stop,
            client_factory=lambda s: FakeClient("fail", [], None),
        ),
        timeout=3,
    )
    assert loop.time() - start < 0.5


async def test_stop_while_idle_exits_promptly() -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    loop.call_later(0.05, stop.set)
    await asyncio.wait_for(
        consumer.run_consumer(
            make_settings(),
            IngestReading(InMemoryReadingRepository()),
            stop,
            client_factory=lambda s: FakeClient("ok_idle", [], None),
        ),
        timeout=3,
    )


async def test_received_messages_are_ingested_and_invalid_ones_do_not_stop_the_loop() -> None:
    repo = InMemoryReadingRepository()
    stop = asyncio.Event()
    body_ok = payload()
    body_next = payload(recorded_at="2026-01-01T12:00:01Z")
    items = [message(body_ok), message(b"{broken"), message(body_next)]
    await asyncio.wait_for(
        consumer.run_consumer(
            make_settings(),
            IngestReading(repo),
            stop,
            client_factory=lambda s: FakeClient("ok", items, stop),
        ),
        timeout=3,
    )
    assert [r.recorded_at.second for r in repo.readings] == [0, 1]


class FlakyRepository(InMemoryReadingRepository):
    """Fails ``failures`` times (None = forever) with an infrastructure error, then works."""

    def __init__(self, failures: int | None) -> None:
        super().__init__()
        self.failures = failures
        self.attempts = 0

    async def add(self, reading: Reading) -> bool:
        self.attempts += 1
        if self.failures is None or self.attempts <= self.failures:
            raise ConnectionError("database down")
        return await super().add(reading)


async def run_with_flaky_repo(
    repo: FlakyRepository, items: list[Any], stop_after_waits: int | None = None
) -> tuple[list[float], list[FakeClient]]:
    stop = asyncio.Event()
    waits: list[float] = []
    clients: list[FakeClient] = []

    def factory(settings: Settings) -> FakeClient:
        client = FakeClient("ok", items, stop)
        clients.append(client)
        return client

    async def fake_wait(_stop: asyncio.Event, seconds: float) -> None:
        waits.append(seconds)
        if stop_after_waits is not None and len(waits) >= stop_after_waits:
            stop.set()
        await asyncio.sleep(0)

    await asyncio.wait_for(
        consumer.run_consumer(
            make_settings(), IngestReading(repo), stop, client_factory=factory, wait=fake_wait
        ),
        timeout=5,
    )
    return waits, clients


async def test_ingest_failure_retries_same_message_with_escalating_backoff() -> None:
    repo = FlakyRepository(failures=7)
    waits, clients = await run_with_flaky_repo(repo, [message(payload())])
    assert waits == [1, 2, 4, 8, 16, 30, 30]
    assert repo.attempts == 8
    assert len(repo.readings) == 1  # stored exactly once after recovery
    assert len(clients) == 1  # never disconnected from the broker


async def test_messages_after_an_outage_are_processed_and_backoff_resets() -> None:
    repo = FlakyRepository(failures=2)
    second = payload(recorded_at="2026-01-01T12:00:01Z")
    items = [message(payload()), message(second)]
    waits, clients = await run_with_flaky_repo(repo, items)
    assert waits == [1, 2]
    assert [r.recorded_at.second for r in repo.readings] == [0, 1]
    assert len(clients) == 1


async def test_backoff_restarts_at_one_for_a_later_outage() -> None:
    repo = FlakyRepository(failures=2)
    items = [message(payload()), message(payload(recorded_at="2026-01-01T12:00:01Z"))]
    original_add = InMemoryReadingRepository.add
    calls = 0

    async def add(self: FlakyRepository, reading: Reading) -> bool:
        nonlocal calls
        calls += 1
        if calls in (1, 2, 4):  # outage, recovery, second outage on the next message
            raise ConnectionError("database down")
        return await original_add(self, reading)

    repo.add = add.__get__(repo)  # type: ignore[method-assign]
    waits, _ = await run_with_flaky_repo(repo, items)
    assert waits == [1, 2, 1]


async def test_stop_during_ingest_retry_exits_and_logs_unstored_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    repo = FlakyRepository(failures=None)
    with caplog.at_level(logging.WARNING):
        waits, clients = await run_with_flaky_repo(repo, [message(payload())], stop_after_waits=2)
    assert waits == [1, 2]
    assert repo.readings == []
    assert len(clients) == 1
    assert any("not stored" in r.getMessage() for r in caplog.records)


async def test_stop_during_real_ingest_wait_exits_promptly() -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    loop.call_later(0.05, stop.set)
    start = loop.time()
    await asyncio.wait_for(
        consumer.run_consumer(
            make_settings(),
            IngestReading(FlakyRepository(failures=None)),
            stop,
            client_factory=lambda s: FakeClient("ok", [message(payload())], None),
        ),
        timeout=3,
    )
    assert loop.time() - start < 0.5


async def test_subscribes_to_the_configured_prefix() -> None:
    settings = make_settings().model_copy(update={"mqtt_topic_prefix": "fermon-test"})
    stop = asyncio.Event()
    clients: list[FakeClient] = []

    def factory(s: Settings) -> FakeClient:
        client = FakeClient("ok", [], stop)
        clients.append(client)
        return client

    await asyncio.wait_for(
        consumer.run_consumer(
            settings, IngestReading(InMemoryReadingRepository()), stop, client_factory=factory
        ),
        timeout=3,
    )
    assert clients[0].subscriptions == [("fermon-test/tanks/+/readings", 1)]


async def test_ready_is_set_after_subscribing() -> None:
    stop = asyncio.Event()
    ready = asyncio.Event()
    client = FakeClient("ok", [], None)
    task = asyncio.create_task(
        consumer.run_consumer(
            make_settings(),
            IngestReading(InMemoryReadingRepository()),
            stop,
            client_factory=lambda s: client,
            ready=ready,
        )
    )
    await asyncio.wait_for(ready.wait(), timeout=3)
    assert client.subscriptions  # ready only after the subscribe succeeded
    stop.set()
    await asyncio.wait_for(task, timeout=3)


def test_default_client_factory_honors_clean_session(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(consumer.aiomqtt, "Client", lambda *a, **kw: captured.update(kw))
    consumer._default_client_factory(make_settings())  # noqa: SLF001
    assert captured["clean_session"] is False
    consumer._default_client_factory(  # noqa: SLF001
        make_settings().model_copy(update={"mqtt_clean_session": True})
    )
    assert captured["clean_session"] is True


# --- transient vs permanent failure classification -------------------------------------------


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (OperationalError("SELECT 1", {}, Exception("down")), True),
        (InterfaceError("SELECT 1", {}, Exception("closed")), True),
        (DBAPIError("SELECT 1", {}, Exception("gone"), connection_invalidated=True), True),
        (ConnectionRefusedError("refused"), True),
        (OSError("network unreachable"), True),
        (TimeoutError(), True),
        (PoolTimeoutError("QueuePool limit reached"), True),
        (DBAPIError("SELECT 1", {}, Exception("bad"), connection_invalidated=False), False),
        (IntegrityError("INSERT", {}, Exception("dup")), False),
        (RuntimeError("bug"), False),
        (ValueError("bad value"), False),
    ],
)
def test_is_transient_classifies_failures(exc: BaseException, expected: bool) -> None:
    assert consumer.is_transient(exc) is expected


class PermanentFailureRepository(InMemoryReadingRepository):
    """Raises a permanent error for the first ``bad`` calls, then works."""

    def __init__(self, error: Exception, bad: int = 1) -> None:
        super().__init__()
        self.error = error
        self.bad = bad
        self.attempts = 0

    async def add(self, reading: Reading) -> bool:
        self.attempts += 1
        if self.attempts <= self.bad:
            raise self.error
        return await super().add(reading)


@pytest.mark.parametrize(
    "error",
    [RuntimeError("boom"), ValueError("bad"), IntegrityError("INSERT", {}, Exception("dup"))],
)
async def test_permanent_failure_is_dropped_without_waiting_and_next_message_is_processed(
    error: Exception, caplog: pytest.LogCaptureFixture
) -> None:
    repo = PermanentFailureRepository(error)
    items = [message(payload()), message(payload(recorded_at="2026-01-01T12:00:01Z"))]
    stop = asyncio.Event()
    waits: list[float] = []

    async def fake_wait(_stop: asyncio.Event, seconds: float) -> None:
        waits.append(seconds)

    with caplog.at_level(logging.ERROR):
        await asyncio.wait_for(
            consumer.run_consumer(
                make_settings(),
                IngestReading(repo),
                stop,
                client_factory=lambda s: FakeClient("ok", items, stop),
                wait=fake_wait,
            ),
            timeout=3,
        )
    assert waits == []
    assert repo.attempts == 2  # poison message attempted once, never retried
    assert [r.recorded_at.second for r in repo.readings] == [1]
    [record] = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert record.exc_info is not None
    assert TOPIC in record.getMessage()
    assert "payload=" in record.getMessage()


async def test_payload_preview_in_drop_log_is_truncated(
    caplog: pytest.LogCaptureFixture,
) -> None:
    repo = PermanentFailureRepository(RuntimeError("boom"))
    huge = payload() + b" " * 5000  # valid JSON padded with whitespace
    with caplog.at_level(logging.ERROR):
        await run_with_flaky_repo_like(repo, [message(huge)])
    [record] = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert "payload=" in record.getMessage()
    assert len(record.getMessage()) < 1000


async def run_with_flaky_repo_like(repo: InMemoryReadingRepository, items: list[Any]) -> None:
    stop = asyncio.Event()
    await asyncio.wait_for(
        consumer.run_consumer(
            make_settings(),
            IngestReading(repo),
            stop,
            client_factory=lambda s: FakeClient("ok", items, stop),
            wait=lambda _s, _t: asyncio.sleep(0),
        ),
        timeout=3,
    )
