import asyncio
import logging
from collections.abc import Awaitable, Callable

from fermon.shared.waiting import sleep_or_stop

logger = logging.getLogger(__name__)


async def run_periodically(
    action: Callable[[], Awaitable[None]],
    interval_seconds: float,
    stop: asyncio.Event,
    *,
    name: str,
    wait: Callable[[asyncio.Event, float], Awaitable[None]] = sleep_or_stop,
) -> None:
    """Run ``action`` every ``interval_seconds`` until ``stop`` is set.

    The first run happens after one interval, not at startup: right after an outage the broker
    backlog is still being ingested and an immediate check would act on stale data. A failing run
    is logged and retried on the next tick; only cancellation ends the loop early.
    """
    while True:
        await wait(stop, interval_seconds)
        if stop.is_set():
            return
        try:
            await action()
        except Exception:
            logger.error("%s failed; retrying in %.0fs", name, interval_seconds, exc_info=True)
