import asyncio

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from fermon.fermentation.infrastructure.persistence import metadata
from fermon.fermentation.infrastructure.schema import alembic_config

pytestmark = pytest.mark.integration

# create_hypertable() adds this index on its own; it is owned by TimescaleDB, not by our
# migration or table metadata, so autogenerate would wrongly propose dropping it.
TIMESCALE_DEFAULT_INDEX = "readings_recorded_at_idx"


def _is_timescale_default_index(diff: object) -> bool:
    return (
        isinstance(diff, tuple)
        and diff[0] == "remove_index"
        and diff[1].name == TIMESCALE_DEFAULT_INDEX
    )


async def test_migrated_schema_matches_table_metadata(migrated_database_url: str) -> None:
    engine = create_async_engine(migrated_database_url)
    try:
        async with engine.connect() as conn:
            diffs = await conn.run_sync(
                lambda sync_conn: compare_metadata(MigrationContext.configure(sync_conn), metadata)
            )
    finally:
        await engine.dispose()
    assert [d for d in diffs if not _is_timescale_default_index(d)] == []


async def test_downgrade_then_upgrade_restores_the_hypertable(migrated_database_url: str) -> None:
    config = alembic_config(migrated_database_url)
    engine = create_async_engine(migrated_database_url)
    try:
        await asyncio.to_thread(command.downgrade, config, "base")
        async with engine.connect() as conn:
            assert await conn.scalar(text("SELECT to_regclass('public.readings')")) is None
        await asyncio.to_thread(command.upgrade, config, "head")
        async with engine.connect() as conn:
            name = await conn.scalar(
                text(
                    "SELECT hypertable_name FROM timescaledb_information.hypertables "
                    "WHERE hypertable_name = 'readings'"
                )
            )
        assert name == "readings"
    finally:
        # Leave the shared session database migrated for the other tests.
        await asyncio.to_thread(command.upgrade, config, "head")
        await engine.dispose()
