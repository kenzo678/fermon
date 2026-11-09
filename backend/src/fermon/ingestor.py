"""Ingestor process: ``python -m fermon.ingestor`` (MQTT -> IngestReading -> database)."""

import asyncio
import logging
import signal
import sys
from collections.abc import Awaitable, Callable

from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from fermon.fermentation.application import IngestReading
from fermon.fermentation.infrastructure.mqtt import run_consumer
from fermon.fermentation.infrastructure.schema import (
    SchemaCheckError,
    SchemaState,
    alembic_config,
    schema_state,
    wait_for_schema,
)
from fermon.fermentation.infrastructure.wiring import (
    alert_rules,
    build_alert_maintenance,
    build_ingest_reading,
)
from fermon.shared.config import Settings
from fermon.shared.db import create_engine, create_session_factory
from fermon.shared.periodic import run_periodically
from fermon.shared.waiting import sleep_or_stop

logger = logging.getLogger(__name__)

SilentCheckFactory = Callable[
    [async_sessionmaker[AsyncSession], Settings], Callable[[], Awaitable[None]]
]


def _default_silent_check(
    sessions: async_sessionmaker[AsyncSession], settings: Settings
) -> Callable[[], Awaitable[None]]:
    return build_alert_maintenance(sessions, alert_rules(settings))


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
    silent_check_factory: SilentCheckFactory = _default_silent_check,
    periodic_wait: Callable[[asyncio.Event, float], Awaitable[None]] = sleep_or_stop,
) -> None:
    """Wait for the migrated schema, then consume until ``stop`` is set.

    Each stored reading triggers alert evaluation (see ``build_ingest_reading``) and, alongside
    the consumer, the alert maintenance (orphan sweep + silent-sensor check) runs every
    ``alert_silent_check_interval_seconds``.

    Raises ``SchemaCheckError`` when the schema can never become ready by waiting.
    """
    engine = engine_factory(settings)
    config = alembic_config(ini_path=settings.alembic_ini_path)
    sessions = create_session_factory(engine)
    ingest = build_ingest_reading(sessions, alert_rules(settings))
    silent_checks: asyncio.Task[None] | None = None
    try:
        # Not consuming while waiting keeps messages queued in the broker's persistent session.
        if await wait_for(lambda: schema_check(engine, config), stop):
            silent_checks = asyncio.create_task(
                run_periodically(
                    silent_check_factory(sessions, settings),
                    settings.alert_silent_check_interval_seconds,
                    stop,
                    name="silent sensor check",
                    wait=periodic_wait,
                )
            )
            await consumer(settings, ingest, stop)
    finally:
        if silent_checks is not None:
            silent_checks.cancel()
            await asyncio.gather(silent_checks, return_exceptions=True)
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
