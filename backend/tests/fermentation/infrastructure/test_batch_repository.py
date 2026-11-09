from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from fermon.fermentation.domain import (
    ActiveBatchConflictError,
    Batch,
    BatchStatus,
    ConcurrentBatchUpdateError,
    StyleTemplate,
    TargetRanges,
)
from fermon.fermentation.infrastructure.persistence import (
    SqlAlchemyBatchRepository,
    SqlAlchemyTankRepository,
)

pytestmark = pytest.mark.integration

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def make_batch(n: int, tank: str = "tank-1", **overrides: Any) -> Batch:
    values: dict[str, Any] = {
        "id": UUID(int=n),
        "tank_id": tank,
        "beer_name": f"Beer {n}",
        "style": "IPA",
        "template": StyleTemplate.ALE,
        "targets": TargetRanges(18.0, 21.0, 1.0, 0.2, 5.0),
        "status": BatchStatus.PLANNED,
        "planned_start": T0,
        "created_at": T0 + timedelta(minutes=n),
        "notes": "n",
        "expected_end": T0 + timedelta(days=10),
    }
    return Batch(**{**values, **overrides})


@pytest.fixture(autouse=True)
async def tanks(tank_repository: SqlAlchemyTankRepository) -> None:
    for tank in ("tank-1", "tank-2", "tank-3"):
        await tank_repository.ensure(tank, T0)


async def test_add_and_get_round_trip_every_field(
    batch_repository: SqlAlchemyBatchRepository,
) -> None:
    batch = make_batch(1)
    bare = make_batch(
        2, notes=None, expected_end=None, targets=TargetRanges(8.0, 12.0, 1.2), tank_id="tank-2"
    )

    await batch_repository.add(batch)
    await batch_repository.add(bare)

    assert await batch_repository.get(batch.id) == batch
    assert await batch_repository.get(bare.id) == bare
    assert await batch_repository.get(UUID(int=99)) is None


async def test_update_replaces_the_stored_batch_and_bumps_its_version(
    batch_repository: SqlAlchemyBatchRepository,
) -> None:
    batch = make_batch(1)
    await batch_repository.add(batch)
    active = batch.start(T0 + timedelta(hours=1))

    await batch_repository.update(active)
    assert await batch_repository.get(batch.id) == active

    finished = active.finish(T0 + timedelta(days=5))
    await batch_repository.update(finished)
    stored = await batch_repository.get(batch.id)
    assert stored == finished and stored.version == 3  # type: ignore[union-attr]


async def test_a_stale_update_loses_and_does_not_revert_the_winner(
    batch_repository: SqlAlchemyBatchRepository,
) -> None:
    # The race from the review: a PATCH loads the planned batch, a start commits meanwhile, then
    # the PATCH writes its stale snapshot. It must not bring the batch back to planned.
    await batch_repository.add(make_batch(1))
    patch_snapshot = await batch_repository.get(UUID(int=1))
    start_snapshot = await batch_repository.get(UUID(int=1))
    assert patch_snapshot is not None and start_snapshot is not None
    started = start_snapshot.start(T0 + timedelta(hours=1))
    await batch_repository.update(started)

    with pytest.raises(ConcurrentBatchUpdateError) as exc:
        await batch_repository.update(patch_snapshot.edit(notes="late edit"))

    assert exc.value.batch_id == str(UUID(int=1))
    assert await batch_repository.get(UUID(int=1)) == started


async def test_update_of_an_unknown_batch_is_a_concurrent_update(
    batch_repository: SqlAlchemyBatchRepository,
) -> None:
    with pytest.raises(ConcurrentBatchUpdateError):
        await batch_repository.update(make_batch(7).edit(notes="ghost"))


async def test_list_filters_and_orders_newest_first(
    batch_repository: SqlAlchemyBatchRepository,
) -> None:
    a, b, c = make_batch(1), make_batch(2, "tank-2"), make_batch(3)
    for batch in (a, b, c):
        await batch_repository.add(batch)
    await batch_repository.update(b.start(T0))

    assert [x.id for x in await batch_repository.list()] == [c.id, b.id, a.id]
    assert [x.id for x in await batch_repository.list(tank_id="tank-1")] == [c.id, a.id]
    assert [x.id for x in await batch_repository.list(status=BatchStatus.ACTIVE)] == [b.id]
    assert await batch_repository.list(tank_id="tank-1", status=BatchStatus.ACTIVE) == []


async def test_active_lookups_by_tank_and_for_many_tanks(
    batch_repository: SqlAlchemyBatchRepository,
) -> None:
    one, two = make_batch(1), make_batch(2, "tank-2")
    await batch_repository.add(one)
    await batch_repository.add(two)
    await batch_repository.add(make_batch(3, "tank-3"))  # stays planned
    await batch_repository.update(one.start(T0))
    two_active = two.start(T0)
    await batch_repository.update(two_active)
    await batch_repository.update(two_active.finish(T0 + timedelta(hours=1)))

    active = await batch_repository.get_active("tank-1")
    assert active is not None and active.id == one.id
    assert await batch_repository.get_active("tank-2") is None
    assert set(await batch_repository.active_for(["tank-1", "tank-2", "tank-3"])) == {"tank-1"}
    assert await batch_repository.active_for([]) == {}


async def test_second_active_batch_in_a_tank_conflicts_through_the_repository(
    batch_repository: SqlAlchemyBatchRepository,
) -> None:
    first, second = make_batch(1), make_batch(2)
    await batch_repository.add(first)
    await batch_repository.add(second)
    await batch_repository.update(first.start(T0))

    with pytest.raises(ActiveBatchConflictError) as exc:
        await batch_repository.update(second.start(T0))

    assert exc.value.tank_id == "tank-1"
    stored = await batch_repository.get(second.id)
    assert stored is not None and stored.status is BatchStatus.PLANNED


async def test_database_enforces_one_active_batch_even_bypassing_the_repository(
    batch_repository: SqlAlchemyBatchRepository, engine: AsyncEngine
) -> None:
    first, second = make_batch(1), make_batch(2)
    await batch_repository.add(first)
    await batch_repository.add(second)
    await batch_repository.update(first.start(T0))

    with pytest.raises(IntegrityError, match="uq_batches_one_active_per_tank"):
        async with engine.begin() as conn:
            await conn.execute(
                text("UPDATE batches SET status = 'active', started_at = now() WHERE id = :id"),
                {"id": second.id},
            )


async def test_database_rejects_unknown_status_and_unknown_tank(
    batch_repository: SqlAlchemyBatchRepository, engine: AsyncEngine
) -> None:
    await batch_repository.add(make_batch(1))

    with pytest.raises(IntegrityError, match="ck_batches_status"):
        async with engine.begin() as conn:
            await conn.execute(text("UPDATE batches SET status = 'paused'"))
    with pytest.raises(IntegrityError, match="fk_batches_tank_id"):
        await batch_repository.add(make_batch(2, "ghost"))
