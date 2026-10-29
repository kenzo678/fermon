import asyncio
from collections.abc import AsyncIterator
from types import SimpleNamespace, TracebackType
from typing import Any

import aiomqtt

from fermon.fermentation.application import IngestReading
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
        mqtt_topic="fermon/tanks/+/readings",
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


async def test_ingest_failure_pauses_with_backoff_and_keeps_running() -> None:
    from tests.fermentation.infrastructure.mqtt.test_handle_message import FailingRepository

    waits, clients = await run_script(["ok", "fail"], [message(payload())], FailingRepository())
    assert waits[0] == 1
    assert len(clients) >= 2
