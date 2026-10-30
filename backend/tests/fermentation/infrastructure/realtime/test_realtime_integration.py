import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import event, func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from fermon.fermentation.domain import MeasurementType, Reading
from fermon.fermentation.infrastructure.persistence import (
    SqlAlchemyReadingRepository,
    reading_repository,
)
from fermon.fermentation.infrastructure.realtime import (
    ReadingBroadcaster,
    listen_dsn,
)
from fermon.fermentation.infrastructure.realtime.payload import READINGS_CHANNEL, encode_reading

pytestmark = pytest.mark.integration

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
READING = Reading("tank-1", "s1", MeasurementType.TEMPERATURE, 18.5, "celsius", T0)


@pytest_asyncio.fixture
async def broadcaster(engine: AsyncEngine) -> AsyncIterator[ReadingBroadcaster]:
    url = engine.url.render_as_string(hide_password=False)
    broadcaster = ReadingBroadcaster(listen_dsn(url))
    await broadcaster.start()
    # NOTIFY is not buffered for absent listeners: wait until the LISTEN is in place.
    await asyncio.wait_for(broadcaster.ready.wait(), timeout=10)
    yield broadcaster
    await broadcaster.stop()


async def test_an_added_reading_reaches_a_real_listener(
    repository: SqlAlchemyReadingRepository, broadcaster: ReadingBroadcaster
) -> None:
    with broadcaster.subscribe("tank-1") as queue:
        assert await repository.add(READING) is True

        assert await asyncio.wait_for(queue.get(), timeout=5) == READING


async def test_a_duplicate_add_notifies_nobody(
    repository: SqlAlchemyReadingRepository, broadcaster: ReadingBroadcaster
) -> None:
    await repository.add(READING)
    with broadcaster.subscribe("tank-1") as queue:
        assert await repository.add(READING) is False
        marker = Reading(
            "tank-1", "s1", MeasurementType.TEMPERATURE, 19.0, "celsius", T0.replace(minute=1)
        )
        await repository.add(marker)

        assert await asyncio.wait_for(queue.get(), timeout=5) == marker
        assert queue.empty()


SILENCE_SECONDS = 0.5

_RAW_INSERT = text(
    "INSERT INTO readings (tank_id, sensor_id, measurement, value, unit, recorded_at) "
    "VALUES ('tank-1', 's1', 'temperature', 18.5, 'celsius', :at)"
)


async def test_postgres_delivers_a_notify_only_when_its_transaction_commits(
    engine: AsyncEngine, broadcaster: ReadingBroadcaster
) -> None:
    # Property of the database the design relies on, exercised on a separate connection:
    # the repository's NOTIFY rides in the inserting transaction, so it inherits this behavior.
    with broadcaster.subscribe("tank-1") as queue:
        async with engine.connect() as conn:
            await conn.execute(_RAW_INSERT, {"at": T0})
            await conn.execute(select(func.pg_notify(READINGS_CHANNEL, encode_reading(READING))))

            await asyncio.sleep(SILENCE_SECONDS)
            assert queue.empty(), "heard a NOTIFY before its transaction committed"

            await conn.commit()
        assert await asyncio.wait_for(queue.get(), timeout=5) == READING


async def test_postgres_never_delivers_a_notify_from_a_rolled_back_transaction(
    engine: AsyncEngine, broadcaster: ReadingBroadcaster
) -> None:
    with broadcaster.subscribe("tank-1") as queue:
        async with engine.connect() as conn:
            await conn.execute(_RAW_INSERT, {"at": T0})
            await conn.execute(select(func.pg_notify(READINGS_CHANNEL, encode_reading(READING))))
            await conn.rollback()

        await asyncio.sleep(SILENCE_SECONDS)
        assert queue.empty()


async def test_repository_issues_its_notify_inside_the_insert_transaction(
    engine: AsyncEngine, repository: SqlAlchemyReadingRepository
) -> None:
    """The repository's own path: INSERT, then pg_notify, then COMMIT, on one connection."""
    events: list[str] = []

    def on_statement(_conn: object, _cur: object, statement: str, *_args: object) -> None:
        if statement.lstrip().upper().startswith("INSERT INTO READINGS"):
            events.append("insert")
        elif "pg_notify" in statement:
            events.append("notify")

    def on_commit(_conn: object) -> None:
        events.append("commit")

    sync_engine = engine.sync_engine
    event.listen(sync_engine, "before_cursor_execute", on_statement)
    event.listen(sync_engine, "commit", on_commit)
    try:
        await repository.add(READING)
    finally:
        event.remove(sync_engine, "before_cursor_execute", on_statement)
        event.remove(sync_engine, "commit", on_commit)

    assert events == ["insert", "notify", "commit"]


async def test_an_oversized_payload_skips_the_notify_but_still_stores_the_reading(
    repository: SqlAlchemyReadingRepository,
    broadcaster: ReadingBroadcaster,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(reading_repository, "MAX_NOTIFY_PAYLOAD_BYTES", 10)
    with broadcaster.subscribe("tank-1") as queue, caplog.at_level(logging.WARNING):
        assert await repository.add(READING) is True

        await asyncio.sleep(SILENCE_SECONDS)
        assert queue.empty()
    assert "payload" in caplog.text
    assert await repository.get("tank-1", "s1", MeasurementType.TEMPERATURE, T0) == READING


async def test_a_failing_notify_does_not_roll_back_the_reading(
    repository: SqlAlchemyReadingRepository,
    broadcaster: ReadingBroadcaster,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # An empty channel name makes PostgreSQL itself reject pg_notify: a genuine NOTIFY error.
    monkeypatch.setattr(
        reading_repository, "_notify_statement", lambda _payload: select(func.pg_notify("", "x"))
    )
    with broadcaster.subscribe("tank-1") as queue, caplog.at_level(logging.WARNING):
        assert await repository.add(READING) is True

        await asyncio.sleep(SILENCE_SECONDS)
        assert queue.empty()
    assert "notify" in caplog.text.lower()
    assert await repository.get("tank-1", "s1", MeasurementType.TEMPERATURE, T0) == READING


async def test_notification_is_delivered_only_once_the_reading_is_committed(
    repository: SqlAlchemyReadingRepository, broadcaster: ReadingBroadcaster
) -> None:
    with broadcaster.subscribe("tank-1") as queue:
        await repository.add(READING)

        heard = await asyncio.wait_for(queue.get(), timeout=5)

    # NOTIFY is queued inside the inserting transaction and delivered at its commit, so by the
    # time anyone hears it the row is visible to other connections.
    stored = await repository.get(
        heard.tank_id, heard.sensor_id, heard.measurement, heard.recorded_at
    )
    assert stored == READING
