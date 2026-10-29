"""Ingestor process: ``python -m fermon.ingestor`` (MQTT -> IngestReading -> database)."""

import asyncio
import logging
import signal

from fermon.fermentation.application import IngestReading
from fermon.fermentation.infrastructure.mqtt import run_consumer
from fermon.fermentation.infrastructure.persistence import SqlAlchemyReadingRepository
from fermon.shared.config import Settings
from fermon.shared.db import create_engine, create_session_factory


async def main(settings: Settings | None = None) -> None:
    settings = settings or Settings()
    engine = create_engine(settings)
    ingest = IngestReading(SqlAlchemyReadingRepository(create_session_factory(engine)))
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    try:
        await run_consumer(settings, ingest, stop)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(main())
