"""Ingestor process: ``python -m fermon.ingestor`` (MQTT -> IngestReading -> database)."""

import asyncio
import logging
import signal
import sys
from collections.abc import Awaitable, Callable

from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncEngine

from fermon.fermentation.application import IngestReading
from fermon.fermentation.infrastructure.mqtt import run_consumer
from fermon.fermentation.infrastructure.persistence import (
    SqlAlchemyReadingRepository,
    SqlAlchemyTankRepository,
)
from fermon.fermentation.infrastructure.schema import (
    SchemaCheckError,
    SchemaState,
    alembic_config,
    schema_state,
    wait_for_schema,
)
from fermon.shared.config import Settings
from fermon.shared.db import create_engine, create_session_factory

logger = logging.getLogger(__name__)


async def run(
    settings: Settings,
    stop: asyncio.Event,
    *,
    engine_factory: Callable[[Settings], AsyncEngine] = create_engine,
    schema_check: Callable[[AsyncEngine, Config], Awaitable[SchemaState]] = schema_state,
    wait_for: Callable[[Callable[[], Awaitable[SchemaState]], asyncio.Event], Awaitable[bool]] = (
        wait_for_schema
    ),
    consumer: Callable[[Settings, IngestReading, asyncio.Event], Awaitable[None]] = run_consumer,
) -> None:
    """Wait for the migrated schema, then consume until ``stop`` is set.

    Raises ``SchemaCheckError`` when the schema can never become ready by waiting.
    """
    engine = engine_factory(settings)
    config = alembic_config(ini_path=settings.alembic_ini_path)
    sessions = create_session_factory(engine)
    ingest = IngestReading(
        SqlAlchemyReadingRepository(sessions), SqlAlchemyTankRepository(sessions)
    )
    try:
        # Not consuming while waiting keeps messages queued in the broker's persistent session.
        if await wait_for(lambda: schema_check(engine, config), stop):
            await consumer(settings, ingest, stop)
    finally:
        await engine.dispose()


async def main(
    settings: Settings | None = None,
    runner: Callable[[Settings, asyncio.Event], Awaitable[None]] = run,
) -> int:
    """Run the ingestor; returns the process exit status."""
    settings = settings or Settings()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    try:
        await runner(settings, stop)
    except SchemaCheckError as exc:
        logger.error(
            "cannot start the ingestor: %s. Check ALEMBIC_INI_PATH, the migrations "
            "directory and that the database revision matches this code.",
            exc,
        )
        return 1
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    sys.exit(asyncio.run(main()))
