from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from fermon.fermentation.application import BuildBatchReport
from fermon.fermentation.domain import (
    Alert,
    AlertKind,
    AlertStatus,
    Batch,
    BatchNotFoundError,
    BatchStatus,
    InvalidBatchTransitionError,
    LabResult,
    MeasurementType,
    QualityParameter,
    QualityProfile,
    QualityStage,
    QualityStatus,
    Reading,
    StyleTemplate,
    TargetRanges,
)
from fermon.fermentation.domain.lab_analysis import LabAnalysis
from tests.fermentation.fakes import (
    InMemoryAlertRepository,
    InMemoryBatchRepository,
    InMemoryLabAnalysisRepository,
    InMemoryQualityProfileRepository,
    InMemoryReadingRepository,
)

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
NOW = T0 + timedelta(hours=5)
PROFILE_ID = UUID(int=500)
ACTIVE, FINISHED, PLANNED, OTHER_TANK = UUID(int=1), UUID(int=2), UUID(int=3), UUID(int=4)
TEMP = MeasurementType.TEMPERATURE


def batch(batch_id: UUID, status: BatchStatus, tank: str, **overrides: object) -> Batch:
    values: dict[str, object] = {
        "id": batch_id,
        "tank_id": tank,
        "beer_name": "Pale Ale",
        "style": "APA",
        "template": StyleTemplate.ALE,
        "targets": TargetRanges(18.0, 21.0, 1.0, None, 5.0),
        "status": status,
        "planned_start": T0 - timedelta(days=1),
        "created_at": T0 - timedelta(days=2),
        "started_at": None if status is BatchStatus.PLANNED else T0,
        "finished_at": T0 + timedelta(hours=2) if status is BatchStatus.FINISHED else None,
    }
    return Batch(**{**values, **overrides})  # type: ignore[arg-type]


def reading(tank: str, minute: int, value: float, measurement: MeasurementType = TEMP) -> Reading:
    at = T0 + timedelta(minutes=minute)
    return Reading(tank, "s1", measurement, value, measurement.unit, at)


async def build(*, max_gap: timedelta = timedelta(minutes=10)) -> BuildBatchReport:
    batches = InMemoryBatchRepository()
    readings = InMemoryReadingRepository()
    alerts = InMemoryAlertRepository()
    profiles = InMemoryQualityProfileRepository()
    analyses = InMemoryLabAnalysisRepository(batches)
    await profiles.add(QualityProfile(id=PROFILE_ID, name="Pale lager", created_at=T0))
    await batches.add(batch(ACTIVE, BatchStatus.ACTIVE, "tank-1", quality_profile_id=PROFILE_ID))
    await batches.add(batch(FINISHED, BatchStatus.FINISHED, "tank-2"))
    await batches.add(batch(PLANNED, BatchStatus.PLANNED, "tank-3"))
    await batches.add(batch(OTHER_TANK, BatchStatus.FINISHED, "tank-4"))
    for tank in ("tank-1", "tank-2"):
        for minute, value in ((0, 19.0), (1, 25.0), (150, 19.0)):  # the last is after the finish
            await readings.add(reading(tank, minute, value))
    await readings.add(reading("tank-1", -30, 5.0))  # before the batch started
    await readings.add(reading("tank-4", 0, 7.0))  # another tank
    await alerts.add(
        Alert(
            id=UUID(int=70),
            tank_id="tank-1",
            batch_id=ACTIVE,
            kind=AlertKind.OUT_OF_RANGE,
            measurement=TEMP,
            status=AlertStatus.OPEN,
            opened_at=T0 + timedelta(minutes=2),
        )
    )
    await analyses.add(
        LabAnalysis(
            id=UUID(int=80),
            batch_id=ACTIVE,
            stage=QualityStage.MATURATION,
            sampled_at=T0 + timedelta(hours=1),
            created_at=T0 + timedelta(hours=2),
            results=(LabResult(QualityParameter.PH, 4.4, QualityStatus.NO_SPEC),),
        )
    )
    return BuildBatchReport(
        batches, readings, alerts, analyses, profiles, clock=lambda: NOW, max_gap=max_gap
    )


async def test_an_active_batch_gets_a_partial_report_up_to_now() -> None:
    use_case = await build()

    report = await use_case.execute(ACTIVE)

    assert report.is_partial
    assert report.generated_at == NOW
    assert report.window_end == NOW
    assert report.profile_name == "Pale lager"
    (temperature,) = report.stats
    assert temperature.count == 3  # the reading before the start is not part of the batch
    assert (temperature.minimum, temperature.maximum) == (19.0, 25.0)


async def test_the_report_gathers_the_alerts_and_analyses_of_the_batch() -> None:
    report = await (await build()).execute(ACTIVE)

    assert [a.id for a in report.alerts] == [UUID(int=70)]
    assert report.alerts[0].ongoing
    assert [a.id for a in report.analyses] == [UUID(int=80)]


async def test_a_finished_batch_is_cut_at_its_finish_time_and_complete() -> None:
    report = await (await build()).execute(FINISHED)

    assert not report.is_partial
    assert report.window_end == T0 + timedelta(hours=2)
    (temperature,) = report.stats
    assert temperature.count == 2  # the reading at +150 min came after the batch finished
    assert report.profile_name is None
    assert report.alerts == ()


async def test_the_gap_cap_comes_from_the_configuration() -> None:
    wide = await (await build(max_gap=timedelta(hours=3))).execute(FINISHED)
    narrow = await (await build(max_gap=timedelta(minutes=1))).execute(FINISHED)

    (wide_temperature,) = wide.stats
    (narrow_temperature,) = narrow.stats
    # samples: 19 at 0, 25 at 1 (min), held until the finish at +120 min
    assert wide_temperature.in_range_percent == pytest.approx(1 / 120 * 100)
    assert narrow_temperature.in_range_percent == pytest.approx(50.0)
    assert wide.max_gap == timedelta(hours=3)


async def test_only_the_readings_of_the_batch_tank_are_reported() -> None:
    report = await (await build()).execute(OTHER_TANK)

    assert [(s.measurement, s.count, s.maximum) for s in report.stats] == [(TEMP, 1, 7.0)]


async def test_a_planned_batch_has_nothing_to_report() -> None:
    with pytest.raises(InvalidBatchTransitionError, match="planned"):
        await (await build()).execute(PLANNED)


async def test_an_unknown_batch_is_not_found() -> None:
    with pytest.raises(BatchNotFoundError):
        await (await build()).execute(UUID(int=999))
