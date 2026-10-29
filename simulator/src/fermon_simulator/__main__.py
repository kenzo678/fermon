import asyncio
import logging
import signal

from fermon_simulator.config import Settings
from fermon_simulator.publisher import run_publisher


async def main() -> None:
    settings = Settings()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    logging.getLogger(__name__).info(
        "simulating %s tanks at acceleration x%s", len(settings.tank_specs), settings.acceleration
    )
    await run_publisher(settings, stop)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(main())
