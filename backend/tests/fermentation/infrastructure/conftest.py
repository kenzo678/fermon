import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from alembic import command
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from fermon.fermentation.infrastructure.persistence import (
    SqlAlchemyReadingRepository,
    SqlAlchemyTankRepository,
)
from fermon.fermentation.infrastructure.schema import alembic_config
from tests.fermentation.infrastructure.database import require_test_database

DEFAULT_TEST_DATABASE_URL = "postgresql+asyncpg://fermon:fermon@timescaledb:5432/fermon_test"


def _test_database_url() -> str:
    return require_test_database(os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL))


async def _ensure_database_exists(url: str) -> None:
    parsed = make_url(url)
    admin = create_async_engine(parsed.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        async with admin.connect() as conn:
            exists = await conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": parsed.database}
            )
            if not exists:
                await conn.execute(text(f'CREATE DATABASE "{parsed.database}"'))
    finally:
        await admin.dispose()


@pytest.fixture(scope="session")
def migrated_database_url() -> str:
    import asyncio

    url = _test_database_url()
    asyncio.run(_ensure_database_exists(url))
    command.upgrade(alembic_config(url), "head")
    return url


@pytest_asyncio.fixture
async def engine(migrated_database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(migrated_database_url)
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE readings, tanks"))
    yield engine
    await engine.dispose()


@pytest.fixture
def repository(engine: AsyncEngine) -> SqlAlchemyReadingRepository:
    return SqlAlchemyReadingRepository(async_sessionmaker(engine, expire_on_commit=False))


@pytest.fixture
def tank_repository(engine: AsyncEngine) -> SqlAlchemyTankRepository:
    return SqlAlchemyTankRepository(async_sessionmaker(engine, expire_on_commit=False))
