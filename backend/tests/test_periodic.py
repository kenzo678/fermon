import asyncio
import logging

import pytest

from fermon.shared.periodic import run_periodically


class Ticker:
    """A fake ``wait`` that records the intervals and stops the loop after ``ticks`` waits."""

    def __init__(self, stop: asyncio.Event, ticks: int) -> None:
        self.stop = stop
        self.ticks = ticks
        self.intervals: list[float] = []

    async def __call__(self, stop: asyncio.Event, seconds: float) -> None:
        self.intervals.append(seconds)
        if len(self.intervals) >= self.ticks:
            stop.set()


async def test_runs_the_action_after_each_wait_until_stopped() -> None:
    stop = asyncio.Event()
    wait = Ticker(stop, ticks=4)
    calls: list[int] = []

    async def action() -> None:
        calls.append(len(wait.intervals))

    await run_periodically(action, 60, stop, wait=wait, name="check")

    # The first wait precedes the first run (no check right at startup); the wait that sets
    # stop is not followed by a run.
    assert calls == [1, 2, 3]
    assert wait.intervals == [60, 60, 60, 60]


async def test_an_action_error_is_logged_and_the_loop_keeps_going(
    caplog: pytest.LogCaptureFixture,
) -> None:
    stop = asyncio.Event()
    wait = Ticker(stop, ticks=4)
    calls = 0

    async def flaky() -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("database down")

    with caplog.at_level(logging.ERROR):
        await run_periodically(flaky, 5, stop, wait=wait, name="silent sensor check")

    assert calls == 3
    assert "silent sensor check failed" in caplog.text


async def test_does_not_run_when_already_stopped() -> None:
    stop = asyncio.Event()
    stop.set()
    calls = 0

    async def action() -> None:
        nonlocal calls
        calls += 1

    await run_periodically(action, 5, stop, name="check")
    assert calls == 0


async def test_cancellation_is_not_swallowed() -> None:
    async def hang() -> None:
        await asyncio.sleep(3600)

    async def tick(stop: asyncio.Event, seconds: float) -> None:
        return None

    task = asyncio.create_task(run_periodically(hang, 1, asyncio.Event(), wait=tick, name="check"))
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
