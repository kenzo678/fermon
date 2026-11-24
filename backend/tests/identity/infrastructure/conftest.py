from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from fermon.identity.infrastructure.persistence import (
    SqlAlchemySessionStore,
    SqlAlchemyUserRepository,
)
from tests.fermentation.infrastructure.conftest import migrated_database_url  # noqa: F401


@pytest_asyncio.fixture
async def identity_engine(migrated_database_url: str) -> AsyncIterator[AsyncEngine]:  # noqa: F811
    engine = create_async_engine(migrated_database_url)
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE sessions, users"))
    yield engine
    await engine.dispose()


@pytest.fixture
def user_repository(identity_engine: AsyncEngine) -> SqlAlchemyUserRepository:
    return SqlAlchemyUserRepository(async_sessionmaker(identity_engine, expire_on_commit=False))


@pytest.fixture
def session_store(identity_engine: AsyncEngine) -> SqlAlchemySessionStore:
    return SqlAlchemySessionStore(async_sessionmaker(identity_engine, expire_on_commit=False))
