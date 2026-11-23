from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest

from fermon.fermentation.domain import (
    Batch,
    BatchNotFoundError,
    BatchStatus,
    LabAnalysis,
    LabResult,
    QualityParameter,
    QualityProfile,
    QualityStage,
    QualityStatus,
    StyleTemplate,
    TargetRanges,
)
from fermon.fermentation.infrastructure.persistence import (
    SqlAlchemyBatchRepository,
    SqlAlchemyLabAnalysisRepository,
    SqlAlchemyQualityProfileRepository,
    SqlAlchemyTankRepository,
)

pytestmark = pytest.mark.integration

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
BATCH_ID = UUID(int=1)
PROFILE_ID = UUID(int=500)
OE = QualityParameter.ORIGINAL_EXTRACT
PH = QualityParameter.PH


def make_analysis(n: int, **overrides: Any) -> LabAnalysis:
    values: dict[str, Any] = {
        "id": UUID(int=100 + n),
        "batch_id": BATCH_ID,
        "stage": QualityStage.BREWHOUSE,
        "sampled_at": T0 + timedelta(hours=n),
        "created_at": T0 + timedelta(hours=n, minutes=5),
        "results": (
            LabResult(OE, 10.45, QualityStatus.WARNING),
            LabResult(PH, 5.2, QualityStatus.IN_SPEC),
        ),
        "analyst": "M. Ruiz",
        "notes": "after fill",
        "quality_profile_id": PROFILE_ID,
    }
    return LabAnalysis(**{**values, **overrides})


@pytest.fixture(autouse=True)
async def batch(
    tank_repository: SqlAlchemyTankRepository,
    batch_repository: SqlAlchemyBatchRepository,
    quality_repository: SqlAlchemyQualityProfileRepository,
) -> None:
    await tank_repository.ensure("tank-1", T0)
    await quality_repository.add(QualityProfile(id=PROFILE_ID, name="Pale lager", created_at=T0))
    await batch_repository.add(
        Batch(
            id=BATCH_ID,
            tank_id="tank-1",
            beer_name="Pale Lager",
            style="Lager",
            template=StyleTemplate.LAGER,
            targets=TargetRanges(8.0, 12.0, 1.2),
            status=BatchStatus.ACTIVE,
            planned_start=T0,
            started_at=T0,
            created_at=T0,
            quality_profile_id=PROFILE_ID,
        )
    )


async def test_add_then_get_round_trips_every_field(
    lab_repository: SqlAlchemyLabAnalysisRepository,
) -> None:
    analysis = make_analysis(1)
    bare = make_analysis(
        2,
        analyst=None,
        notes=None,
        quality_profile_id=None,
        results=(LabResult(PH, 4.3, QualityStatus.NO_SPEC),),
    )

    await lab_repository.add(analysis)
    await lab_repository.add(bare)

    assert await lab_repository.get(analysis.id) == analysis
    assert await lab_repository.get(bare.id) == bare
    assert await lab_repository.get(UUID(int=999)) is None


async def test_list_for_batch_orders_by_sample_time_and_filters_by_stage(
    lab_repository: SqlAlchemyLabAnalysisRepository,
) -> None:
    late = make_analysis(3)
    early = make_analysis(1)
    packaged = make_analysis(2, stage=QualityStage.PACKAGED)
    for analysis in (late, early, packaged):
        await lab_repository.add(analysis)

    every = await lab_repository.list_for_batch(BATCH_ID)
    brewhouse = await lab_repository.list_for_batch(BATCH_ID, QualityStage.BREWHOUSE)

    assert [a.id for a in every] == [early.id, packaged.id, late.id]
    assert [a.id for a in brewhouse] == [early.id, late.id]
    assert await lab_repository.list_for_batch(UUID(int=2)) == []


async def test_add_for_an_unknown_batch_is_not_found_and_stores_nothing(
    lab_repository: SqlAlchemyLabAnalysisRepository,
) -> None:
    orphan = make_analysis(1, batch_id=UUID(int=2), quality_profile_id=None)

    with pytest.raises(BatchNotFoundError):
        await lab_repository.add(orphan)

    assert await lab_repository.get(orphan.id) is None
