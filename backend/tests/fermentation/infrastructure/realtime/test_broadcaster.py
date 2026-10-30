import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest

from fermon.fermentation.domain import MeasurementType, Reading
from fermon.fermentation.infrastructure.realtime.broadcaster import (
    ReadingBroadcaster,
    listen_dsn,
)
from fermon.fermentation.infrastructure.realtime.payload import READINGS_CHANNEL, encode_reading
from fermon.shared.waiting import sleep_or_stop

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def reading(tank: str = "tank-1", value: float = 18.0) -> Reading:
    return Reading(tank, "s1", MeasurementType.TEMPERATURE, value, "celsius", T0)


class FakeConnection:
    def __init__(self) -> None:
        self.listeners: dict[str, Callable[..., None]] = {}
        self.termination: list[Callable[[Any], None]] = []
        self.closed = False
        self.hang = False
        self.hang_close = False
        self.terminated = False
        self.health_checks = 0

    async def execute(self, query: str) -> str:
        self.health_checks += 1
        if self.hang:
            await asyncio.Event().wait()  # a half-open socket never answers
        return "SELECT 1"

    async def add_listener(self, channel: str, callback: Callable[..., None]) -> None:
        self.listeners[channel] = callback

    def add_termination_listener(self, callback: Callable[[Any], None]) -> None:
        self.termination.append(callback)

    async def close(self) -> None:
        if self.hang_close:
            await asyncio.Event().wait()
        self.closed = True

    def terminate(self) -> None:
        self.terminated = True

    def notify(self, payload: str) -> None:
        self.listeners[READINGS_CHANNEL](self, 1, READINGS_CHANNEL, payload)

    def drop(self) -> None:
        for callback in self.termination:
            callback(self)


class Harness:
    """Fake connection factory: yields queued outcomes (connections or exceptions)."""

    def __init__(self, *outcomes: FakeConnection | Exception) -> None:
        self.outcomes = list(outcomes)
        self.dsns: list[str] = []
        self.waits: list[float] = []
        self.connected = asyncio.Event()
        self.waited = asyncio.Event()

    async def connect(self, dsn: str) -> FakeConnection:
        self.dsns.append(dsn)
        outcome = self.outcomes.pop(0) if self.outcomes else OSError("no more")
        if isinstance(outcome, Exception):
            raise outcome
        self.connected.set()
        return outcome

    async def wait(self, stop: asyncio.Event, seconds: float) -> None:
        self.waits.append(seconds)
        self.waited.set()
        await asyncio.sleep(0)

    def broadcaster(self, **kwargs: Any) -> ReadingBroadcaster:
        return ReadingBroadcaster(
            "postgresql://u:p@db/x", connect=self.connect, wait=self.wait, **kwargs
        )


async def next_message(queue: asyncio.Queue[Reading]) -> Reading:
    return await asyncio.wait_for(queue.get(), timeout=2)


async def started(harness: Harness, **kwargs: Any) -> ReadingBroadcaster:
    broadcaster = harness.broadcaster(**kwargs)
    await broadcaster.start()
    await asyncio.wait_for(harness.connected.wait(), timeout=2)
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    return broadcaster


def test_listen_dsn_drops_the_sqlalchemy_driver_and_keeps_the_password() -> None:
    dsn = listen_dsn("postgresql+asyncpg://fermon:s3cr%40t@timescaledb:5432/fermon")

    assert dsn == "postgresql://fermon:s3cr%40t@timescaledb:5432/fermon"


async def test_fans_out_each_reading_only_to_subscribers_of_its_tank() -> None:
    conn = FakeConnection()
    broadcaster = await started(Harness(conn))
    try:
        with broadcaster.subscribe("tank-1") as one, broadcaster.subscribe("tank-1") as two:
            with broadcaster.subscribe("tank-2") as other:
                conn.notify(encode_reading(reading("tank-1", 18.0)))
                conn.notify(encode_reading(reading("tank-2", 12.0)))

                assert (await next_message(one)).value == 18.0
                assert (await next_message(two)).value == 18.0
                assert (await next_message(other)).value == 12.0
                assert one.empty() and two.empty() and other.empty()
    finally:
        await broadcaster.stop()


async def test_malformed_payload_is_dropped_with_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    conn = FakeConnection()
    broadcaster = await started(Harness(conn))
    try:
        with broadcaster.subscribe("tank-1") as queue, caplog.at_level(logging.WARNING):
            conn.notify("{broken")
            conn.notify(encode_reading(reading()))

            assert (await next_message(queue)).tank_id == "tank-1"
            assert queue.empty()
        assert "malformed" in caplog.text
    finally:
        await broadcaster.stop()


async def test_slow_subscriber_drops_its_oldest_messages_without_affecting_others(
    caplog: pytest.LogCaptureFixture,
) -> None:
    conn = FakeConnection()
    broadcaster = await started(Harness(conn), queue_size=3)
    try:
        with broadcaster.subscribe("tank-1") as slow, broadcaster.subscribe("tank-1") as fast:
            with caplog.at_level(logging.DEBUG):
                for value in (1.0, 2.0, 3.0, 4.0, 5.0):
                    conn.notify(encode_reading(reading(value=value)))
                    assert (await next_message(fast)).value == value

            assert [slow.get_nowait().value for _ in range(slow.qsize())] == [3.0, 4.0, 5.0]
        assert "dropped oldest" in caplog.text
    finally:
        await broadcaster.stop()


async def test_leaving_the_context_removes_the_subscription() -> None:
    conn = FakeConnection()
    broadcaster = await started(Harness(conn))
    try:
        with broadcaster.subscribe("tank-1"):
            assert broadcaster.subscriber_count("tank-1") == 1
        assert broadcaster.subscriber_count("tank-1") == 0

        with pytest.raises(RuntimeError), broadcaster.subscribe("tank-1"):
            raise RuntimeError("boom")
        assert broadcaster.subscriber_count("tank-1") == 0
    finally:
        await broadcaster.stop()


async def test_connection_failures_back_off_exponentially_then_reset_after_success() -> None:
    conn = FakeConnection()
    harness = Harness(OSError("down"), OSError("down"), OSError("down"), conn, FakeConnection())
    broadcaster = await started(harness)
    try:
        assert harness.waits == [1.0, 2.0, 4.0]

        harness.waited.clear()
        conn.drop()
        await asyncio.wait_for(harness.waited.wait(), timeout=2)

        # After a success the sequence restarts at 1 s instead of continuing from 8 s.
        assert harness.waits == [1.0, 2.0, 4.0, 1.0]
        for _ in range(100):
            if len(harness.dsns) >= 5:
                break
            await asyncio.sleep(0)
        assert len(harness.dsns) == 5
    finally:
        await broadcaster.stop()


async def test_backoff_is_capped_at_thirty_seconds() -> None:
    harness = Harness(*[OSError("down")] * 8)
    broadcaster = harness.broadcaster()
    await broadcaster.start()
    try:
        for _ in range(100):
            if len(harness.waits) >= 8:
                break
            await asyncio.sleep(0)
        assert harness.waits[:8] == [1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 30.0, 30.0]
    finally:
        await broadcaster.stop()


async def test_reconnect_delivers_new_readings_to_existing_subscribers(
    caplog: pytest.LogCaptureFixture,
) -> None:
    first, second = FakeConnection(), FakeConnection()
    harness = Harness(first, second)
    with caplog.at_level(logging.WARNING):
        broadcaster = await started(harness)
        try:
            with broadcaster.subscribe("tank-1") as queue:
                first.drop()
                for _ in range(100):
                    if READINGS_CHANNEL in second.listeners:
                        break
                    await asyncio.sleep(0)
                second.notify(encode_reading(reading(value=7.0)))

                assert (await next_message(queue)).value == 7.0
                assert first.closed
            assert "connection lost" in caplog.text
        finally:
            await broadcaster.stop()


async def test_stop_is_prompt_while_waiting_to_reconnect_and_closes_the_connection() -> None:
    failing = ReadingBroadcaster(
        "postgresql://x/y", connect=Harness(*[OSError("down")] * 50).connect, wait=sleep_or_stop
    )
    await failing.start()
    await asyncio.sleep(0.05)
    await asyncio.wait_for(failing.stop(), timeout=1)

    conn = FakeConnection()
    live = await started(Harness(conn))
    await live.stop()
    assert conn.closed


async def wait_until(condition: Callable[[], bool], timeout: float = 2.0) -> None:
    async with asyncio.timeout(timeout):
        while not condition():
            await asyncio.sleep(0.005)


async def test_unexpected_error_is_logged_retried_and_does_not_kill_the_listener(
    caplog: pytest.LogCaptureFixture,
) -> None:
    conn = FakeConnection()
    harness = Harness(ValueError("boom"), conn)
    with caplog.at_level(logging.ERROR):
        broadcaster = await started(harness)
        try:
            with broadcaster.subscribe("tank-1") as queue:
                conn.notify(encode_reading(reading(value=3.0)))

                assert (await next_message(queue)).value == 3.0
            assert harness.waits == [1.0]
            errors = [r for r in caplog.records if r.levelno == logging.ERROR]
            assert errors and errors[0].exc_info is not None
            assert "boom" in caplog.text
        finally:
            await broadcaster.stop()


async def test_stop_does_not_raise_after_an_unexpected_error() -> None:
    harness = Harness(ValueError("boom"))
    broadcaster = harness.broadcaster()
    await broadcaster.start()
    await asyncio.wait_for(harness.waited.wait(), timeout=2)

    await asyncio.wait_for(broadcaster.stop(), timeout=2)


async def test_ready_is_set_once_listening_and_cleared_when_the_connection_is_lost() -> None:
    conn = FakeConnection()
    harness = Harness(conn)
    broadcaster = harness.broadcaster()
    assert not broadcaster.ready.is_set()
    await broadcaster.start()
    try:
        await asyncio.wait_for(broadcaster.ready.wait(), timeout=2)
        assert READINGS_CHANNEL in conn.listeners

        conn.drop()
        await asyncio.wait_for(harness.waited.wait(), timeout=2)

        assert not broadcaster.ready.is_set()
    finally:
        await broadcaster.stop()


async def test_a_connection_whose_health_query_times_out_is_replaced(
    caplog: pytest.LogCaptureFixture,
) -> None:
    half_open, healthy = FakeConnection(), FakeConnection()
    half_open.hang = True
    harness = Harness(half_open, healthy)
    with caplog.at_level(logging.WARNING):
        broadcaster = await started(harness, health_interval=0.01, health_timeout=0.02)
        try:
            await wait_until(lambda: len(harness.dsns) >= 2)

            assert half_open.closed
            assert "health check" in caplog.text
        finally:
            await broadcaster.stop()


async def test_a_healthy_connection_is_checked_periodically_and_kept() -> None:
    conn = FakeConnection()
    harness = Harness(conn)
    broadcaster = await started(harness, health_interval=0.01, health_timeout=0.5)
    try:
        await wait_until(lambda: conn.health_checks >= 3)

        assert len(harness.dsns) == 1
        assert not conn.closed
    finally:
        await broadcaster.stop()


async def test_stop_returns_promptly_while_connect_is_blocked() -> None:
    entered = asyncio.Event()

    async def hanging_connect(dsn: str) -> FakeConnection:
        entered.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    broadcaster = ReadingBroadcaster(
        "postgresql://u:p@db/x", connect=hanging_connect, stop_grace=0.05
    )
    await broadcaster.start()
    await asyncio.wait_for(entered.wait(), timeout=2)
    task = broadcaster._task
    assert task is not None

    await asyncio.wait_for(broadcaster.stop(), timeout=1)

    assert task.done()


async def test_a_hanging_close_after_a_failed_health_check_falls_back_to_terminate() -> None:
    half_open, healthy = FakeConnection(), FakeConnection()
    half_open.hang = True
    half_open.hang_close = True
    harness = Harness(half_open, healthy)
    broadcaster = await started(
        harness, health_interval=0.01, health_timeout=0.02, close_timeout=0.02
    )
    try:
        await wait_until(lambda: len(harness.dsns) >= 2)

        assert half_open.terminated
    finally:
        await broadcaster.stop()


async def test_stop_cancelling_a_hanging_close_still_terminates_the_connection() -> None:
    connection = FakeConnection()
    connection.hang_close = True
    harness = Harness(connection)
    broadcaster = await started(harness, stop_grace=0.05, close_timeout=10.0)
    await wait_until(lambda: len(harness.dsns) >= 1)

    await asyncio.wait_for(broadcaster.stop(), timeout=2)

    assert connection.terminated
