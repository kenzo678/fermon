from datetime import UTC, datetime, timedelta
from itertools import count
from uuid import UUID

from fermon.fermentation.application import (
    CheckSilentSensors,
    EvaluateReadingAlerts,
    FinishBatch,
    ResolveBatchAlerts,
    ResolveOrphanAlerts,
)
from fermon.fermentation.domain import (
    Alert,
    AlertKind,
    AlertRules,
    AlertStatus,
    Batch,
    BatchStatus,
    MeasurementType,
    Reading,
    StyleTemplate,
    TargetRanges,
)
from tests.fermentation.fakes import (
    InMemoryAlertRepository,
    InMemoryBatchRepository,
    InMemoryReadingRepository,
)

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
TEMP = MeasurementType.TEMPERATURE
PRESSURE = MeasurementType.PRESSURE
UNITS = {TEMP: "celsius", PRESSURE: "bar", MeasurementType.ALCOHOL: "percent_abv"}
TARGETS = TargetRanges(18.0, 21.0, 1.0)


def make_batch(
    n: int = 1,
    tank: str = "tank-1",
    status: BatchStatus = BatchStatus.ACTIVE,
    started_at: datetime | None = T0,
) -> Batch:
    return Batch(
        id=UUID(int=n),
        tank_id=tank,
        beer_name="Beer",
        style="IPA",
        template=StyleTemplate.CUSTOM,
        targets=TARGETS,
        status=status,
        planned_start=T0,
        created_at=T0,
        started_at=started_at if status is not BatchStatus.PLANNED else None,
        finished_at=T0 + timedelta(hours=1) if status is BatchStatus.FINISHED else None,
    )


class World:
    """Fakes plus helpers; ``feed`` stores a reading and runs the evaluator, like ingest does."""

    def __init__(self) -> None:
        self.readings = InMemoryReadingRepository()
        self.batches = InMemoryBatchRepository()
        self.alerts = InMemoryAlertRepository()
        ids = count(100)
        self.evaluate = EvaluateReadingAlerts(
            self.readings,
            self.batches,
            self.alerts,
            AlertRules(),
            new_id=lambda: UUID(int=next(ids)),
        )
        self.now = T0
        self.silent = CheckSilentSensors(
            self.readings,
            self.batches,
            self.alerts,
            AlertRules(),
            clock=lambda: self.now,
            new_id=lambda: UUID(int=next(ids)),
        )

    async def feed(
        self,
        minutes: float,
        value: float,
        measurement: MeasurementType = TEMP,
        tank: str = "tank-1",
    ) -> None:
        reading = Reading(
            tank, "s1", measurement, value, UNITS[measurement], T0 + timedelta(minutes=minutes)
        )
        await self.readings.add(reading)
        await self.evaluate.execute(reading)

    async def stored(self, **filters: object) -> list:  # type: ignore[type-arg]
        return await self.alerts.list(**filters)  # type: ignore[arg-type]


async def world_with_active_batch() -> World:
    world = World()
    await world.batches.add(make_batch())
    return world


async def test_violation_held_for_five_minutes_opens_exactly_one_alert() -> None:
    world = await world_with_active_batch()
    for minute in range(0, 5):  # 0..4: held for 4 minutes at the last one
        await world.feed(minute, 25.0)
    assert await world.stored() == []

    await world.feed(5, 25.0)
    await world.feed(6, 26.0)
    await world.feed(7, 27.0)

    [alert] = await world.stored()
    assert (alert.kind, alert.measurement, alert.status) == (
        AlertKind.OUT_OF_RANGE,
        TEMP,
        AlertStatus.OPEN,
    )
    assert (alert.tank_id, alert.batch_id) == ("tank-1", UUID(int=1))
    assert alert.opened_at == T0 + timedelta(minutes=5)
    assert alert.details == {
        "observed": 25.0,
        "bound": "above",
        "target_min": 18.0,
        "target_max": 21.0,
    }


async def test_four_minutes_fifty_nine_seconds_does_not_open() -> None:
    world = await world_with_active_batch()
    await world.feed(0, 25.0)
    await world.feed(4.98333, 25.0)  # 4:59
    assert await world.stored() == []


async def test_below_the_minimum_records_the_violated_bound() -> None:
    world = await world_with_active_batch()
    await world.feed(0, 15.0)
    await world.feed(5, 14.0)
    [alert] = await world.stored()
    assert alert.details["bound"] == "below" and alert.details["observed"] == 14.0


async def test_a_dip_back_into_range_restarts_the_sustained_clock() -> None:
    world = await world_with_active_batch()
    await world.feed(0, 25.0)
    await world.feed(3, 25.0)
    await world.feed(4, 20.0)  # back in range: the violation was not continuous
    await world.feed(6, 25.0)
    await world.feed(10, 25.0)  # only 4 minutes since it started again
    assert await world.stored() == []

    await world.feed(11, 25.0)
    assert len(await world.stored()) == 1


async def test_back_in_range_for_two_minutes_resolves_the_alert() -> None:
    world = await world_with_active_batch()
    await world.feed(0, 25.0)
    await world.feed(5, 25.0)
    await world.feed(6, 20.0)
    await world.feed(7.5, 20.0)  # 1.5 minutes in range: still open
    [still_open] = await world.stored()
    assert still_open.status is AlertStatus.OPEN

    await world.feed(8, 20.0)

    [resolved] = await world.stored()
    assert resolved.status is AlertStatus.RESOLVED
    assert resolved.resolved_at == T0 + timedelta(minutes=8)


async def test_flapping_inside_the_resolve_window_does_not_resolve() -> None:
    world = await world_with_active_batch()
    await world.feed(0, 25.0)
    await world.feed(5, 25.0)
    for minute, value in [(6, 20.0), (6.5, 25.0), (7.5, 20.0), (8.5, 25.0), (9.5, 20.0)]:
        await world.feed(minute, value)
    [alert] = await world.stored()
    assert alert.status is AlertStatus.OPEN

    await world.feed(11.5, 20.0)  # now two minutes in range since 9.5
    [alert] = await world.stored()
    assert alert.status is AlertStatus.RESOLVED


async def test_an_acknowledged_alert_blocks_duplicates_and_still_auto_resolves() -> None:
    world = await world_with_active_batch()
    await world.feed(0, 25.0)
    await world.feed(5, 25.0)
    [alert] = await world.stored()
    await world.alerts.update(alert.acknowledge(T0 + timedelta(minutes=6)))

    await world.feed(7, 25.0)
    assert len(await world.stored()) == 1

    await world.feed(8, 20.0)
    await world.feed(10, 20.0)
    [resolved] = await world.stored()
    assert resolved.status is AlertStatus.RESOLVED
    assert resolved.acknowledged_at == T0 + timedelta(minutes=6)


async def test_a_new_violation_after_resolution_opens_a_new_alert() -> None:
    world = await world_with_active_batch()
    await world.feed(0, 25.0)
    await world.feed(5, 25.0)
    await world.feed(6, 20.0)
    await world.feed(8, 20.0)
    await world.feed(9, 25.0)
    await world.feed(14, 25.0)

    statuses = sorted(a.status.value for a in await world.stored())
    assert statuses == ["open", "resolved"]


async def test_evaluating_the_same_reading_twice_keeps_one_alert() -> None:
    world = await world_with_active_batch()
    await world.feed(0, 25.0)
    reading = Reading("tank-1", "s1", TEMP, 25.0, "celsius", T0 + timedelta(minutes=5))
    await world.readings.add(reading)
    await world.evaluate.execute(reading)
    await world.evaluate.execute(reading)
    assert len(await world.stored()) == 1


async def test_temperature_and_pressure_alert_independently() -> None:
    world = await world_with_active_batch()
    for minute in (0, 5):
        await world.feed(minute, 25.0, TEMP)
        await world.feed(minute, 0.5, PRESSURE)  # in range for pressure
    assert [a.measurement for a in await world.stored()] == [TEMP]

    for minute in (6, 11):
        await world.feed(minute, 2.0, PRESSURE)
    assert {a.measurement for a in await world.stored()} == {TEMP, PRESSURE}


async def test_no_active_batch_means_no_evaluation() -> None:
    world = World()
    await world.feed(0, 25.0)
    await world.feed(10, 25.0)
    assert await world.stored() == []


async def test_planned_and_finished_batches_are_not_evaluated() -> None:
    world = World()
    await world.batches.add(make_batch(1, "tank-1", BatchStatus.PLANNED))
    await world.batches.add(make_batch(2, "tank-2", BatchStatus.FINISHED))
    for tank in ("tank-1", "tank-2"):
        await world.feed(0, 25.0, tank=tank)
        await world.feed(10, 25.0, tank=tank)
    assert await world.stored() == []


async def test_another_tanks_batch_is_not_used() -> None:
    world = World()
    await world.batches.add(make_batch(1, "tank-2"))
    await world.feed(0, 25.0, tank="tank-1")
    await world.feed(10, 25.0, tank="tank-1")
    assert await world.stored() == []


async def test_alcohol_never_alerts() -> None:
    world = await world_with_active_batch()
    await world.feed(0, 19.0, MeasurementType.ALCOHOL)
    await world.feed(10, 19.0, MeasurementType.ALCOHOL)
    assert await world.stored() == []


async def test_readings_from_before_the_batch_started_do_not_count() -> None:
    world = World()
    await world.batches.add(make_batch(started_at=T0 + timedelta(minutes=10)))
    await world.feed(0, 25.0)  # old violation, before the batch
    await world.feed(12, 25.0)
    await world.feed(16, 25.0)  # only 4 minutes since the first reading of the batch
    assert await world.stored() == []

    await world.feed(17, 25.0)
    assert len(await world.stored()) == 1


async def test_an_unresolved_silent_alert_is_resolved_by_any_new_reading() -> None:
    world = await world_with_active_batch()
    world.now = T0 + timedelta(minutes=10)
    await world.silent.execute()
    [silent] = await world.stored(kind=AlertKind.SILENT_SENSOR)
    assert silent.status is AlertStatus.OPEN

    await world.feed(11, 5.0, MeasurementType.ALCOHOL)

    [silent] = await world.stored(kind=AlertKind.SILENT_SENSOR)
    assert silent.status is AlertStatus.RESOLVED
    assert silent.resolved_at == T0 + timedelta(minutes=11)


async def silent_alert_world() -> World:
    """A tank whose last reading was at minute 0 and whose silent alert opened at minute 10."""
    world = await world_with_active_batch()
    await world.feed(0, 20.0)
    world.now = T0 + timedelta(minutes=10)
    await world.silent.execute()
    return world


async def test_a_backlog_reading_older_than_the_alert_resolves_it_as_late_data() -> None:
    world = await silent_alert_world()

    await world.feed(5, 20.0)  # recorded before the alert opened: the sensor was reporting

    [silent] = await world.stored(kind=AlertKind.SILENT_SENSOR)
    assert silent.status is AlertStatus.RESOLVED
    assert silent.resolved_at == silent.opened_at == T0 + timedelta(minutes=10)
    assert silent.details["resolution"] == "late_data"
    assert silent.details["last_reading_at"] == T0.isoformat()


async def test_a_reading_not_newer_than_the_alert_evidence_does_not_resolve_it() -> None:
    world = await silent_alert_world()
    older_or_equal = [
        Reading("tank-1", "s2", TEMP, 20.0, "celsius", T0),  # same instant as the evidence
        Reading("tank-1", "s2", TEMP, 20.0, "celsius", T0 - timedelta(minutes=3)),
    ]
    for reading in older_or_equal:
        await world.readings.add(reading)
        await world.evaluate.execute(reading)

    [silent] = await world.stored(kind=AlertKind.SILENT_SENSOR)
    assert silent.status is AlertStatus.OPEN


async def test_a_reading_after_the_alert_resolves_it_normally_without_a_marker() -> None:
    world = await silent_alert_world()

    await world.feed(12, 20.0)

    [silent] = await world.stored(kind=AlertKind.SILENT_SENSOR)
    assert silent.resolved_at == T0 + timedelta(minutes=12)
    assert "resolution" not in silent.details


async def test_a_late_out_of_range_reading_cannot_open_an_alert_in_a_range_known_in_range() -> None:
    world = await world_with_active_batch()
    await world.feed(0, 25.0)  # out of range
    await world.feed(6, 20.0)  # newer: back in range
    await world.feed(7, 20.0)
    # A backlog reading from minute 5 would complete 5 minutes out of range if evaluated at 5.
    await world.feed(5, 25.0)

    assert await world.stored() == []


async def test_a_late_in_range_reading_does_not_resolve_while_newer_readings_are_out_of_range() -> (
    None
):
    world = await world_with_active_batch()
    await world.feed(0, 25.0)
    await world.feed(5, 25.0)
    await world.feed(8, 25.0)  # newest: still out of range
    [alert] = await world.stored()
    assert alert.status is AlertStatus.OPEN

    await world.feed(2, 20.0)  # old in-range readings arrive late
    await world.feed(3, 20.0)
    await world.feed(4.5, 20.0)

    [alert] = await world.stored()
    assert alert.status is AlertStatus.OPEN


async def test_a_late_reading_is_evaluated_as_of_the_newest_stored_reading() -> None:
    # Characterization: already held before anchoring; pins that opened_at is the newest time.
    world = await world_with_active_batch()
    await world.feed(0, 25.0)
    await world.feed(5, 20.0)
    await world.feed(5.5, 25.0)
    await world.feed(10.5, 25.0)  # out of range since 5.5 -> 5 min: opens at the newest time
    await world.feed(1, 25.0)  # late, same class as the newest

    [alert] = await world.stored()
    assert alert.opened_at == T0 + timedelta(minutes=10.5)


async def test_silent_check_opens_once_after_ten_minutes_without_readings() -> None:
    world = await world_with_active_batch()
    await world.feed(0, 20.0)

    world.now = T0 + timedelta(minutes=9, seconds=59)
    await world.silent.execute()
    assert await world.stored() == []

    world.now = T0 + timedelta(minutes=10)
    await world.silent.execute()
    world.now = T0 + timedelta(minutes=11)
    await world.silent.execute()

    [alert] = await world.stored()
    assert (alert.kind, alert.measurement, alert.status) == (
        AlertKind.SILENT_SENSOR,
        None,
        AlertStatus.OPEN,
    )
    assert alert.batch_id == UUID(int=1)
    assert alert.details == {"last_reading_at": T0.isoformat()}
    assert alert.opened_at == T0 + timedelta(minutes=10)


async def test_silent_check_counts_from_the_batch_start_when_it_never_reported() -> None:
    world = World()
    await world.batches.add(make_batch(started_at=T0))
    await world.feed(-30, 20.0)  # before the batch: does not count as activity

    world.now = T0 + timedelta(minutes=9)
    await world.silent.execute()
    assert await world.stored() == []

    world.now = T0 + timedelta(minutes=10)
    await world.silent.execute()
    [alert] = await world.stored()
    assert alert.details == {"last_reading_at": None}


async def test_silent_check_ignores_planned_and_finished_batches() -> None:
    world = World()
    await world.batches.add(make_batch(1, "tank-1", BatchStatus.PLANNED))
    await world.batches.add(make_batch(2, "tank-2", BatchStatus.FINISHED))
    world.now = T0 + timedelta(hours=5)
    await world.silent.execute()
    assert await world.stored() == []


async def test_silence_after_a_resolved_silent_alert_opens_a_new_one() -> None:
    world = await world_with_active_batch()
    world.now = T0 + timedelta(minutes=10)
    await world.silent.execute()
    await world.feed(11, 20.0)

    world.now = T0 + timedelta(minutes=21)
    await world.silent.execute()

    assert sorted(a.status.value for a in await world.stored()) == ["open", "resolved"]


# --- Alerts of batches that are no longer active ----------------------------------------------


def make_alert(
    n: int,
    batch: int,
    status: AlertStatus = AlertStatus.OPEN,
    measurement: MeasurementType = TEMP,
) -> Alert:
    acknowledged = T0 if status is AlertStatus.ACKNOWLEDGED else None
    return Alert(
        id=UUID(int=n),
        tank_id=f"tank-{batch}",
        batch_id=UUID(int=batch),
        kind=AlertKind.OUT_OF_RANGE,
        measurement=measurement,
        status=status,
        opened_at=T0,
        acknowledged_at=acknowledged,
        details={"observed": 25.0},
    )


async def test_finishing_a_batch_resolves_its_open_and_acknowledged_alerts_only() -> None:
    world = World()
    for n in (1, 2):
        await world.batches.add(make_batch(n, tank=f"tank-{n}"))
    open_alert = make_alert(11, batch=1)
    acked = make_alert(12, 1, AlertStatus.ACKNOWLEDGED, PRESSURE)
    other = make_alert(13, batch=2)
    resolved = make_alert(14, batch=1).resolve(T0)
    for alert in (open_alert, acked, other, resolved):
        await world.alerts.add(alert)
    finish_time = T0 + timedelta(hours=2)
    finish = FinishBatch(
        world.batches,
        lambda: finish_time,
        after_finished=ResolveBatchAlerts(world.alerts).execute,
    )

    await finish.execute(UUID(int=1))

    stored = {a.id: a for a in await world.alerts.list()}
    for alert in (open_alert, acked):
        done = stored[alert.id]
        assert (done.status, done.resolved_at) == (AlertStatus.RESOLVED, finish_time)
        assert done.details["resolution"] == "batch_finished"
    assert stored[other.id].status is AlertStatus.OPEN
    assert "resolution" not in stored[resolved.id].details
    assert stored[resolved.id].resolved_at == T0


async def test_sweep_resolves_orphans_of_finished_and_planned_batches_not_active_ones() -> None:
    world = World()
    await world.batches.add(make_batch(1, tank="tank-1"))  # active
    await world.batches.add(make_batch(2, tank="tank-2", status=BatchStatus.FINISHED))
    await world.batches.add(make_batch(3, tank="tank-3", status=BatchStatus.PLANNED))
    await world.alerts.add(make_alert(11, batch=1))
    await world.alerts.add(make_alert(12, batch=2))
    await world.alerts.add(make_alert(13, batch=3, status=AlertStatus.ACKNOWLEDGED))
    world.now = T0 + timedelta(hours=3)
    sweep = ResolveOrphanAlerts(world.batches, world.alerts, clock=lambda: world.now)

    await sweep.execute()
    await sweep.execute()  # idempotent

    stored = {a.id: a for a in await world.alerts.list()}
    assert stored[UUID(int=11)].status is AlertStatus.OPEN
    for n in (12, 13):
        assert stored[UUID(int=n)].status is AlertStatus.RESOLVED
        assert stored[UUID(int=n)].resolved_at == world.now
        assert stored[UUID(int=n)].details["resolution"] == "batch_finished"
        assert stored[UUID(int=n)].version == 2  # resolved once, not again by the 2nd sweep


async def test_a_series_sparser_than_any_window_still_opens_and_resolves() -> None:
    world = await world_with_active_batch()
    await world.feed(0, 20.0)
    await world.feed(60, 25.0)
    assert await world.stored() == []

    await world.feed(120, 25.0)  # held 60 min, the readings are an hour apart
    [alert] = await world.stored()
    assert alert.opened_at == T0 + timedelta(minutes=120)

    await world.feed(180, 20.0)
    await world.feed(240, 20.0)
    assert (await world.stored())[0].status is AlertStatus.RESOLVED
