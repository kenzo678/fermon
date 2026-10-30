import asyncio


async def sleep_or_stop(stop: asyncio.Event, seconds: float) -> None:
    """Sleep for ``seconds`` or until ``stop`` is set, whichever comes first."""
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
    except TimeoutError:
        pass
