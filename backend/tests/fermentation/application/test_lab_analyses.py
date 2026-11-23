from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest

from fermon.fermentation.application import (
    GetLabAnalysis,
    ListLabAnalyses,
    RecordLabAnalysis,
    RecordLabAnalysisCommand,
)
from fermon.fermentation.domain import (
    Batch,
    BatchNotFoundError,
    BatchStatus,
    InvalidBatchTransitionError,
    InvalidLabAnalysisError,
    LabAnalysisNotFoundError,
    LabResult,
    QualityParameter,
    QualityProfile,
    QualitySpec,
    QualityStage,
    QualityStatus,
    SpecRange,
    StyleTemplate,
    TargetRanges,
)
from tests.fermentation.fakes import (
    InMemoryBatchRepository,
    InMemoryLabAnalysisRepository,
    InMemoryQualityProfileRepository,
)

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
NOW = T0 + timedelta(hours=6)
PROFILE_ID = UUID(int=500)
LINKED, UNLINKED, PLANNED, UNKNOWN = UUID(int=1), UUID(int=2), UUID(int=3), UUID(int=99)
OE = QualityParameter.ORIGINAL_EXTRACT
PH = QualityParameter.PH
BREWHOUSE = QualityStage.BREWHOUSE
OE_SPEC = QualitySpec(BREWHOUSE, OE, SpecRange(9.9, 10.5), SpecRange(10.0, 10.4))


class Ids:
    def __init__(self) -> None:
        self.n = 100

    def __call__(self) -> UUID:
        self.n += 1
        return UUID(int=self.n)


def batch(batch_id: UUID, **overrides: Any) -> Batch:
    values: dict[str, Any] = {
        "id": batch_id,
        "tank_id": f"tank-{batch_id.int}",
        "beer_name": "Pale Lager",
        "style": "Lager",
        "template": StyleTemplate.LAGER,
        "targets": TargetRanges(8.0, 12.0, 1.2),
        "status": BatchStatus.ACTIVE,
        "planned_start": T0,
        "started_at": T0,
        "created_at": T0,
    }
    return Batch(**{**values, **overrides})


class World:
    def __init__(self) -> None:
        self.batches = InMemoryBatchRepository()
        self.profiles = InMemoryQualityProfileRepository()
        self.analyses = InMemoryLabAnalysisRepository(self.batches)
        self.record = RecordLabAnalysis(
            self.batches, self.profiles, self.analyses, clock=lambda: NOW, new_id=Ids()
        )
        self.list = ListLabAnalyses(self.batches, self.analyses)
        self.get = GetLabAnalysis(self.analyses)


@pytest.fixture
async def world() -> World:
    w = World()
    profile = QualityProfile(id=PROFILE_ID, name="Pale lager", created_at=T0, specs=(OE_SPEC,))
    await w.profiles.add(profile)
    await w.batches.add(batch(LINKED, quality_profile_id=PROFILE_ID))
    await w.batches.add(batch(UNLINKED))
    await w.batches.add(batch(PLANNED, status=BatchStatus.PLANNED, started_at=None))
    return w


def command(**overrides: Any) -> RecordLabAnalysisCommand:
    values: dict[str, Any] = {"stage": BREWHOUSE, "values": {OE: 10.45, PH: 5.2}}
    return RecordLabAnalysisCommand(**{**values, **overrides})


async def test_record_judges_values_against_the_batch_profile_and_stores_it(world: World) -> None:
    analysis = await world.record.execute(LINKED, command(analyst="M. Ruiz", notes="after fill"))

    assert analysis.id == UUID(int=101)
    assert (analysis.sampled_at, analysis.created_at) == (NOW, NOW)  # sampled_at defaults to now
    assert analysis.quality_profile_id == PROFILE_ID
    assert analysis.results == (
        LabResult(OE, 10.45, QualityStatus.WARNING),
        LabResult(PH, 5.2, QualityStatus.NO_SPEC),
    )
    assert (analysis.analyst, analysis.notes) == ("M. Ruiz", "after fill")
    assert await world.analyses.get(analysis.id) == analysis


async def test_record_keeps_an_explicit_sample_time(world: World) -> None:
    sampled = NOW - timedelta(hours=3)

    analysis = await world.record.execute(LINKED, command(sampled_at=sampled))

    assert analysis.sampled_at == sampled


async def test_a_batch_without_profile_records_no_spec(world: World) -> None:
    analysis = await world.record.execute(UNLINKED, command())

    assert analysis.quality_profile_id is None
    assert {r.status for r in analysis.results} == {QualityStatus.NO_SPEC}


async def test_statuses_are_a_snapshot_of_the_spec_when_recorded(world: World) -> None:
    analysis = await world.record.execute(LINKED, command())
    wider = QualitySpec(BREWHOUSE, OE, SpecRange(9.0, 11.0), SpecRange(9.5, 10.8))
    await world.profiles.save_spec(PROFILE_ID, wider)

    stored = await world.get.execute(analysis.id)

    assert stored.results[0] == LabResult(OE, 10.45, QualityStatus.WARNING)


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"values": {}}, "values"),
        ({"values": {"gravity": 1.0}}, "values.gravity"),
        ({"values": {PH: 15.0}}, "values.ph"),
        ({"sampled_at": NOW + timedelta(minutes=1)}, "sampled_at"),
    ],
)
async def test_invalid_analyses_store_nothing(
    world: World, overrides: dict[str, Any], field: str
) -> None:
    with pytest.raises(InvalidLabAnalysisError) as error:
        await world.record.execute(LINKED, command(**overrides))

    assert error.value.field == field
    assert world.analyses.analyses == {}


async def test_unknown_or_planned_batches_cannot_be_analyzed(world: World) -> None:
    with pytest.raises(BatchNotFoundError):
        await world.record.execute(UNKNOWN, command())
    with pytest.raises(InvalidBatchTransitionError):
        await world.record.execute(PLANNED, command())

    assert world.analyses.analyses == {}


async def test_list_orders_by_sample_time_and_filters_by_stage(world: World) -> None:
    late = await world.record.execute(LINKED, command(sampled_at=NOW - timedelta(hours=1)))
    early = await world.record.execute(LINKED, command(sampled_at=NOW - timedelta(hours=5)))
    packaged = await world.record.execute(
        LINKED, command(stage=QualityStage.PACKAGED, sampled_at=NOW - timedelta(hours=3))
    )
    await world.record.execute(UNLINKED, command())

    every = await world.list.execute(LINKED)
    brewhouse = await world.list.execute(LINKED, BREWHOUSE)

    assert [a.id for a in every] == [early.id, packaged.id, late.id]
    assert [a.id for a in brewhouse] == [early.id, late.id]


async def test_list_for_an_unknown_batch_is_not_found(world: World) -> None:
    with pytest.raises(BatchNotFoundError):
        await world.list.execute(UNKNOWN)


async def test_get_an_unknown_analysis_is_not_found(world: World) -> None:
    with pytest.raises(LabAnalysisNotFoundError):
        await world.get.execute(UNKNOWN)
