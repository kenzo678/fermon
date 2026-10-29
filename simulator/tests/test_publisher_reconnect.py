import asyncio
from types import TracebackType
from typing import Any

import aiomqtt

from fermon_simulator import publisher
from fermon_simulator.config import Settings


def make_settings() -> Settings:
    return Settings(  # type: ignore[call-arg]
        _env_file=None, tanks="tank-1:ale", seed=1, tick_interval_seconds=0.01
    )


class FakeClient:
    """Scripted client: each connect attempt consumes one outcome ('fail', 'drop', 'ok')."""

    def __init__(self, outcome: str) -> None:
        self.outcome = outcome
        self.published = 0

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

    async def publish(self, topic: str, payload: Any, qos: int = 0) -> None:
        if self.outcome == "drop":
            raise aiomqtt.MqttError("connection lost")
        self.published += 1


async def run_script(outcomes: list[str]) -> list[float]:
    """Run the publisher through scripted outcomes; return every wait duration requested."""
    stop = asyncio.Event()
    waits: list[float] = []
    script = iter(outcomes)

    def factory(host: str, port: int) -> FakeClient:
        try:
            return FakeClient(next(script))
        except StopIteration:
            stop.set()
            return FakeClient("ok")

    async def fake_wait(_stop: asyncio.Event, seconds: float) -> None:
        waits.append(seconds)

    await asyncio.wait_for(
        publisher.run_publisher(make_settings(), stop, client_factory=factory, wait=fake_wait),
        timeout=5,
    )
    return waits


async def test_backoff_doubles_and_caps_at_thirty_seconds() -> None:
    waits = await run_script(["fail"] * 8)
    assert waits == [1, 2, 4, 8, 16, 30, 30, 30]


async def test_backoff_resets_after_successful_connect() -> None:
    waits = await run_script(["fail", "fail", "fail", "drop", "fail"])
    # 1, 2, 4 while failing; connect succeeds then drops -> reset, so next wait is 1 again.
    assert waits == [1, 2, 4, 1, 2]


async def test_stop_during_backoff_exits_promptly() -> None:
    stop = asyncio.Event()

    def factory(host: str, port: int) -> FakeClient:
        return FakeClient("fail")

    loop = asyncio.get_running_loop()
    loop.call_later(0.05, stop.set)
    start = loop.time()
    await asyncio.wait_for(
        publisher.run_publisher(make_settings(), stop, client_factory=factory), timeout=3
    )
    assert loop.time() - start < 0.5


async def test_publishes_readings_while_connected() -> None:
    stop = asyncio.Event()
    clients: list[FakeClient] = []

    def factory(host: str, port: int) -> FakeClient:
        clients.append(FakeClient("ok"))
        return clients[-1]

    async def stop_after_first_tick(_stop: asyncio.Event, seconds: float) -> None:
        stop.set()

    await publisher.run_publisher(
        make_settings(), stop, client_factory=factory, wait=stop_after_first_tick
    )
    assert len(clients) == 1
    assert clients[0].published > 0


async def test_sleep_or_stop_returns_when_stopped() -> None:
    stop = asyncio.Event()
    stop.set()
    await asyncio.wait_for(publisher._sleep_or_stop(stop, 30), timeout=1)
