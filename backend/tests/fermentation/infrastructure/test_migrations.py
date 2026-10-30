import asyncio
from datetime import UTC, datetime, timedelta

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


async def test_tanks_migration_backfills_tanks_from_existing_readings(
    migrated_database_url: str,
) -> None:
    config = alembic_config(migrated_database_url)
    engine = create_async_engine(migrated_database_url)
    insert = text(
        "INSERT INTO readings (tank_id, sensor_id, measurement, value, unit, recorded_at) "
        "VALUES (:tank, 's', 'temperature', 18, 'celsius', :at)"
    )
    try:
        await asyncio.to_thread(command.downgrade, config, "0001")
        async with engine.begin() as conn:
            assert await conn.scalar(text("SELECT to_regclass('public.tanks')")) is None
            await conn.execute(text("TRUNCATE readings"))
            for tank, at in [
                ("tank-b", datetime(2026, 1, 2, tzinfo=UTC)),
                ("tank-a", datetime(2026, 1, 3, tzinfo=UTC)),
                ("tank-a", datetime(2026, 1, 1, tzinfo=UTC)),
            ]:
                await conn.execute(insert, {"tank": tank, "at": at})

        await asyncio.to_thread(command.upgrade, config, "head")

        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    text("SELECT id, display_name, first_seen_at FROM tanks ORDER BY id")
                )
            ).all()
        assert [(r.id, r.display_name, r.first_seen_at) for r in rows] == [
            ("tank-a", None, datetime(2026, 1, 1, tzinfo=UTC)),
            ("tank-b", None, datetime(2026, 1, 2, tzinfo=UTC)),
        ]
    finally:
        await asyncio.to_thread(command.upgrade, config, "head")
        async with engine.begin() as conn:
            await conn.execute(text("TRUNCATE readings, tanks"))
        await engine.dispose()


async def test_aggregates_are_real_time_with_refresh_policies_and_are_dropped_on_downgrade(
    migrated_database_url: str,
) -> None:
    config = alembic_config(migrated_database_url)
    engine = create_async_engine(migrated_database_url)
    views = text(
        "SELECT view_name, materialized_only FROM timescaledb_information.continuous_aggregates "
        "ORDER BY view_name"
    )
    # In TimescaleDB 2.31 the refresh jobs report the continuous aggregate's view name.
    policies = text(
        "SELECT hypertable_name, config->>'start_offset', config->>'end_offset', schedule_interval "
        "FROM timescaledb_information.jobs WHERE proc_name = 'policy_refresh_continuous_aggregate' "
        "ORDER BY hypertable_name"
    )
    try:
        async with engine.connect() as conn:
            assert [tuple(r) for r in await conn.execute(views)] == [
                ("readings_1h", False),
                ("readings_1m", False),
            ]
            assert [tuple(r) for r in await conn.execute(policies)] == [
                ("readings_1h", "3 days", "01:00:00", timedelta(minutes=30)),
                ("readings_1m", "02:00:00", "00:01:00", timedelta(minutes=1)),
            ]

        await asyncio.to_thread(command.downgrade, config, "0002")
        async with engine.connect() as conn:
            assert list(await conn.execute(views)) == []
            assert list(await conn.execute(policies)) == []
            assert await conn.scalar(text("SELECT to_regclass('public.readings')")) is not None
    finally:
        await asyncio.to_thread(command.upgrade, config, "head")
        await engine.dispose()
