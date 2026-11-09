from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from fermon.fermentation.application import (
    CreateBatch,
    CreateBatchCommand,
    FinishBatch,
    GetActiveBatch,
    GetBatch,
    GetTank,
    ListBatches,
    ListTanks,
    StartBatch,
    UpdateBatch,
)
from fermon.fermentation.domain import (
    ActiveBatchConflictError,
    Batch,
    BatchNotFoundError,
    BatchStatus,
    ConcurrentBatchUpdateError,
    InvalidBatchError,
    InvalidBatchTransitionError,
    StyleTemplate,
    TankNotFoundError,
    TargetRanges,
)
from tests.fermentation.fakes import (
    InMemoryBatchRepository,
    InMemoryReadingRepository,
    InMemoryTankRepository,
)

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now


class Ids:
    def __init__(self) -> None:
        self.n = 0

    def __call__(self) -> UUID:
        self.n += 1
        return UUID(int=self.n)


class World:
    def __init__(self) -> None:
        self.tanks = InMemoryTankRepository()
        self.batches = InMemoryBatchRepository()
        self.readings = InMemoryReadingRepository()
        self.clock = Clock()
        self.create = CreateBatch(self.batches, self.tanks, self.clock, Ids())
        self.update = UpdateBatch(self.batches)
        self.start = StartBatch(self.batches, self.clock)
        self.finish = FinishBatch(self.batches, self.clock)


async def world() -> World:
    w = World()
    for tank in ("tank-1", "tank-2"):
        await w.tanks.ensure(tank, T0)
    return w


def command(**overrides: object) -> CreateBatchCommand:
    values: dict[str, object] = {"tank_id": "tank-1", "beer_name": "Pale Ale", "style": "APA"}
    return CreateBatchCommand(**{**values, "template": StyleTemplate.ALE, **overrides})  # type: ignore[arg-type]


# --- Create ---------------------------------------------------------------------------------


async def test_create_uses_the_template_targets_and_defaults_to_a_planned_batch_now() -> None:
    w = await world()

    batch = await w.create.execute(command(tank_id=" tank-1 "))

    assert batch.status is BatchStatus.PLANNED
    assert batch.tank_id == "tank-1"
    assert batch.targets == TargetRanges(18.0, 21.0, 1.0, None, 5.0)
    assert batch.planned_start == T0 and batch.created_at == T0
    assert await w.batches.get(batch.id) == batch


async def test_create_explicit_target_fields_override_the_template() -> None:
    w = await world()

    batch = await w.create.execute(
        command(
            template=StyleTemplate.LAGER, targets={"temperature_max": 13.0, "pressure_min": 0.2}
        )
    )

    assert batch.targets == TargetRanges(8.0, 13.0, 1.2, 0.2, 5.2)


async def test_create_custom_requires_the_mandatory_targets() -> None:
    w = await world()

    with pytest.raises(InvalidBatchError) as exc:
        await w.create.execute(
            command(template=StyleTemplate.CUSTOM, targets={"temperature_min": 10.0})
        )
    assert exc.value.field == "temperature_max"

    custom = await w.create.execute(
        command(
            template=StyleTemplate.CUSTOM,
            targets={"temperature_min": 10.0, "temperature_max": 14.0, "pressure_max": 1.5},
        )
    )
    assert custom.targets == TargetRanges(10.0, 14.0, 1.5)


async def test_create_rejects_invalid_or_unknown_target_fields() -> None:
    w = await world()

    with pytest.raises(InvalidBatchError) as exc:
        await w.create.execute(command(targets={"temperature_min": 25.0}))
    assert exc.value.field == "temperature_max"
    with pytest.raises(InvalidBatchError) as exc:
        await w.create.execute(command(targets={"humidity": 3.0}))
    assert exc.value.field == "humidity"


async def test_create_requires_a_registered_tank() -> None:
    w = await world()

    with pytest.raises(TankNotFoundError):
        await w.create.execute(command(tank_id="nope"))
    assert w.batches.batches == {}


async def test_create_rejects_a_blank_name_and_a_bad_schedule() -> None:
    w = await world()

    with pytest.raises(InvalidBatchError) as exc:
        await w.create.execute(command(beer_name=" "))
    assert exc.value.field == "beer_name"
    with pytest.raises(InvalidBatchError) as exc:
        await w.create.execute(command(planned_start=T0, expected_end=T0))
    assert exc.value.field == "expected_end"


# --- Update ---------------------------------------------------------------------------------


async def test_update_changes_only_the_given_fields_and_merges_targets() -> None:
    w = await world()
    batch = await w.create.execute(command())

    updated = await w.update.execute(
        batch.id, {"notes": "dry hop", "targets": {"temperature_max": 22.0}}
    )

    assert updated.notes == "dry hop" and updated.beer_name == "Pale Ale"
    assert updated.targets == TargetRanges(18.0, 22.0, 1.0, None, 5.0)
    assert await w.batches.get(batch.id) == updated


async def test_empty_update_is_a_no_op_that_keeps_the_version() -> None:
    # A PATCH with nothing to change must not bump the version and cause spurious 409s elsewhere.
    w = await world()
    batch = await w.create.execute(command())

    unchanged = await w.update.execute(batch.id, {}, expected_version=batch.version)

    assert unchanged == batch
    assert (await w.batches.get(batch.id)).version == batch.version


async def test_updates_that_change_nothing_do_not_write_or_bump_the_version() -> None:
    w = await world()
    batch = await w.create.execute(command(notes="same"))
    no_ops: list[dict[str, object]] = [
        {"targets": {}},
        {"targets": None},
        {"notes": "same"},
        {"notes": "same", "targets": {"temperature_max": batch.targets.temperature_max}},
    ]

    for changes in no_ops:
        unchanged = await w.update.execute(batch.id, changes, expected_version=batch.version)  # type: ignore[arg-type]
        assert unchanged == batch, changes

    assert await w.batches.get(batch.id) == batch


async def test_a_real_change_still_bumps_the_version() -> None:
    w = await world()
    batch = await w.create.execute(command(notes="same"))

    updated = await w.update.execute(batch.id, {"notes": "other"})

    assert (updated.notes, updated.version) == ("other", batch.version + 1)


async def test_update_can_clear_an_optional_target() -> None:
    w = await world()
    batch = await w.create.execute(command())

    updated = await w.update.execute(batch.id, {"targets": {"expected_final_abv": None}})

    assert updated.targets.expected_final_abv is None


async def test_update_unknown_batch_and_finished_batch() -> None:
    w = await world()
    with pytest.raises(BatchNotFoundError):
        await w.update.execute(UUID(int=99), {"notes": "x"})

    batch = await w.create.execute(command())
    await w.start.execute(batch.id)
    await w.finish.execute(batch.id)
    with pytest.raises(InvalidBatchTransitionError):
        await w.update.execute(batch.id, {"notes": "x"})


async def test_update_invalid_values_leave_the_batch_untouched() -> None:
    w = await world()
    batch = await w.create.execute(command())

    with pytest.raises(InvalidBatchError):
        await w.update.execute(batch.id, {"targets": {"temperature_min": 99.0}})

    assert await w.batches.get(batch.id) == batch


async def test_update_with_a_stale_expected_version_is_rejected_and_changes_nothing() -> None:
    w = await world()
    batch = await w.create.execute(command())
    await w.start.execute(batch.id)  # bumps the stored version to 2

    with pytest.raises(ConcurrentBatchUpdateError):
        await w.update.execute(batch.id, {"notes": "x"}, expected_version=batch.version)

    stored = await w.batches.get(batch.id)
    assert stored is not None and stored.notes is None and stored.status is BatchStatus.ACTIVE


async def test_update_with_the_current_expected_version_succeeds() -> None:
    w = await world()
    batch = await w.create.execute(command())

    updated = await w.update.execute(batch.id, {"notes": "x"}, expected_version=1)

    assert updated.version == 2 and updated.notes == "x"


async def test_a_stale_snapshot_cannot_revert_a_concurrent_start() -> None:
    w = await world()
    batch = await w.create.execute(command())
    stale = batch.edit(notes="late edit")  # what an UpdateBatch that loaded before the start holds
    await w.start.execute(batch.id)

    with pytest.raises(ConcurrentBatchUpdateError):
        await w.batches.update(stale)

    stored = await w.batches.get(batch.id)
    assert stored is not None and stored.status is BatchStatus.ACTIVE


async def test_create_start_and_finish_advance_the_version() -> None:
    w = await world()
    batch = await w.create.execute(command())

    started = await w.start.execute(batch.id)
    finished = await w.finish.execute(batch.id)

    assert (batch.version, started.version, finished.version) == (1, 2, 3)


# --- Start / finish -------------------------------------------------------------------------


async def test_start_and_finish_stamp_the_clock() -> None:
    w = await world()
    batch = await w.create.execute(command())

    w.clock.now = T0 + timedelta(hours=1)
    started = await w.start.execute(batch.id)
    w.clock.now = T0 + timedelta(days=7)
    finished = await w.finish.execute(batch.id)

    assert (started.status, started.started_at) == (BatchStatus.ACTIVE, T0 + timedelta(hours=1))
    assert (finished.status, finished.finished_at) == (BatchStatus.FINISHED, T0 + timedelta(days=7))
    assert await w.batches.get(batch.id) == finished


async def test_only_one_active_batch_per_tank_but_other_tanks_are_independent() -> None:
    w = await world()
    first = await w.create.execute(command())
    second = await w.create.execute(command(beer_name="Second"))
    elsewhere = await w.create.execute(command(tank_id="tank-2"))
    await w.start.execute(first.id)

    with pytest.raises(ActiveBatchConflictError) as exc:
        await w.start.execute(second.id)
    assert exc.value.tank_id == "tank-1"
    assert (await w.batches.get(second.id)).status is BatchStatus.PLANNED  # type: ignore[union-attr]
    await w.start.execute(elsewhere.id)

    await w.finish.execute(first.id)
    assert (await w.start.execute(second.id)).status is BatchStatus.ACTIVE


async def test_invalid_transitions_and_unknown_batches() -> None:
    w = await world()
    batch = await w.create.execute(command())

    with pytest.raises(InvalidBatchTransitionError):
        await w.finish.execute(batch.id)  # not started
    await w.start.execute(batch.id)
    with pytest.raises(InvalidBatchTransitionError):
        await w.start.execute(batch.id)  # already active (not a "conflict" with itself)
    with pytest.raises(BatchNotFoundError):
        await w.start.execute(UUID(int=99))
    with pytest.raises(BatchNotFoundError):
        await w.finish.execute(UUID(int=99))


# --- Queries --------------------------------------------------------------------------------


async def test_get_and_list_with_filters_newest_first() -> None:
    w = await world()
    a = await w.create.execute(command())
    w.clock.now = T0 + timedelta(minutes=1)
    b = await w.create.execute(command(tank_id="tank-2"))
    w.clock.now = T0 + timedelta(minutes=2)
    c = await w.create.execute(command(beer_name="Third"))
    await w.start.execute(b.id)

    assert await GetBatch(w.batches).execute(a.id) == a
    with pytest.raises(BatchNotFoundError):
        await GetBatch(w.batches).execute(UUID(int=99))
    listing = ListBatches(w.batches)
    assert [x.id for x in await listing.execute()] == [c.id, b.id, a.id]
    assert [x.id for x in await listing.execute(tank_id=" tank-1 ")] == [c.id, a.id]
    assert [x.id for x in await listing.execute(status=BatchStatus.ACTIVE)] == [b.id]
    assert await listing.execute(tank_id="tank-2", status=BatchStatus.PLANNED) == []


async def test_get_active_batch_by_tank() -> None:
    w = await world()
    batch = await w.create.execute(command())
    get_active = GetActiveBatch(w.batches)

    assert await get_active.execute("tank-1") is None
    await w.start.execute(batch.id)
    active = await get_active.execute(" tank-1 ")
    assert active is not None and active.id == batch.id
    assert await get_active.execute("tank-2") is None


# --- Tank overview --------------------------------------------------------------------------


async def test_tank_overviews_include_the_active_batch() -> None:
    w = await world()
    batch = await w.create.execute(command())
    await w.create.execute(command(beer_name="Waiting"))
    await w.start.execute(batch.id)

    overviews = await ListTanks(w.tanks, w.readings, w.batches).execute()
    one = await GetTank(w.tanks, w.readings, w.batches).execute("tank-1")

    assert [o.active_batch for o in overviews] == [(await w.batches.get(batch.id)), None]
    assert one.active_batch is not None and one.active_batch.id == batch.id


async def test_finish_runs_the_after_finished_hook_with_the_finished_batch() -> None:
    w = await world()
    seen: list[Batch] = []

    async def hook(batch: Batch) -> None:
        seen.append(batch)

    finish = FinishBatch(w.batches, w.clock, after_finished=hook)
    batch = await w.create.execute(command())
    await w.start.execute(batch.id)

    finished = await finish.execute(batch.id)

    assert seen == [finished]


async def test_a_failing_after_finished_hook_never_fails_the_finish() -> None:
    w = await world()

    async def broken(batch: Batch) -> None:
        raise RuntimeError("alerts are down")

    finish = FinishBatch(w.batches, w.clock, after_finished=broken)
    batch = await w.create.execute(command())
    await w.start.execute(batch.id)

    finished = await finish.execute(batch.id)

    assert finished.status is BatchStatus.FINISHED
    assert await w.batches.get(batch.id) == finished
