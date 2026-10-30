"""Database schema readiness: lets the ingestor wait for ``alembic upgrade head``.

The ingestor must not consume messages before the schema exists: the resulting errors would be
permanent per message and every reading would be dropped. While it waits, the MQTT persistent
session keeps the messages queued at the broker.
"""

import asyncio
import enum
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from alembic.util.exc import CommandError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from fermon.shared.config import DEFAULT_ALEMBIC_INI_PATH
from fermon.shared.waiting import sleep_or_stop

logger = logging.getLogger(__name__)

INITIAL_BACKOFF_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 30.0


class SchemaState(enum.Enum):
    READY = "ready"
    # No version table or an older known revision: ``alembic upgrade head`` will fix it.
    BEHIND = "behind"
    # The database revision is not in this code's migration history (database ahead or diverged).
    UNKNOWN_REVISION = "unknown_revision"


class SchemaCheckError(Exception):
    """The schema cannot become ready by waiting: a deployment or configuration problem."""


def alembic_config(url: str | None = None, ini_path: Path | None = None) -> Config:
    """Build an Alembic config that does not depend on the current working directory.

    A relative ``script_location`` is resolved against the directory of the ini file.
    """
    ini = ini_path or DEFAULT_ALEMBIC_INI_PATH
    config = Config(str(ini))
    if not config.file_config.has_section(config.config_ini_section):
        # Missing/empty ini: let the failure surface from the script directory check instead.
        config.file_config.add_section(config.config_ini_section)
    location = Path(config.get_main_option("script_location") or "migrations")
    if not location.is_absolute():
        location = ini.parent / location
    config.set_main_option("script_location", str(location))
    if url is not None:
        config.set_main_option("sqlalchemy.url", url)
    return config


def classify_revision(script: ScriptDirectory, revision: str | None) -> SchemaState:
    """Classify the database's current ``revision`` against the migration scripts."""
    if revision is None:
        return SchemaState.BEHIND
    known = {r.revision for r in script.walk_revisions()}
    if revision not in known:
        return SchemaState.UNKNOWN_REVISION
    return SchemaState.READY if revision == script.get_current_head() else SchemaState.BEHIND


async def schema_state(engine: AsyncEngine, config: Config) -> SchemaState:
    """Compare the database's Alembic revision with the script history.

    Raises ``alembic.util.exc.CommandError`` for Alembic configuration problems (missing script
    directory, multiple heads), before touching the database.
    """
    script = ScriptDirectory.from_config(config)
    script.get_current_head()  # raises CommandError on multiple heads
    async with engine.connect() as connection:
        revision = await connection.run_sync(
            lambda sync: MigrationContext.configure(sync).get_current_revision()
        )
    return classify_revision(script, revision)


async def wait_for_schema(
    check: Callable[[], Awaitable[SchemaState]],
    stop: asyncio.Event,
    wait: Callable[[asyncio.Event, float], Awaitable[None]] = sleep_or_stop,
) -> bool:
    """Poll ``check`` with capped exponential backoff (1 s to 30 s) until the schema is READY.

    Returns False as soon as ``stop`` is set. Database connectivity failures and a BEHIND schema
    count as "not ready". Raises ``SchemaCheckError`` for problems waiting cannot fix: Alembic
    configuration errors and a database revision this code does not know.
    """
    backoff = INITIAL_BACKOFF_SECONDS
    while not stop.is_set():
        try:
            state = await check()
        except CommandError as exc:
            raise SchemaCheckError(f"Alembic configuration error: {exc}") from exc
        except (SQLAlchemyError, OSError, TimeoutError) as exc:
            logger.warning(
                "database unavailable (%r); retrying in %.0fs while waiting for the schema",
                exc,
                backoff,
            )
        else:
            if state is SchemaState.READY:
                logger.info("database schema is ready")
                return True
            if state is SchemaState.UNKNOWN_REVISION:
                raise SchemaCheckError(
                    "the database is at an Alembic revision this code does not know "
                    "(database ahead or diverged); deploy the code version that matches it"
                )
            logger.warning(
                "database schema not ready: migrations are not applied; "
                "run `alembic upgrade head`; retrying in %.0fs",
                backoff,
            )
        await wait(stop, backoff)
        backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)
    return False
