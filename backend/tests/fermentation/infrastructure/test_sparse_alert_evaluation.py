from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from fermon.fermentation.application import EvaluateReadingAlerts
from fermon.fermentation.domain import (
    AlertRules,
    AlertStatus,
    Batch,
    BatchStatus,
    MeasurementType,
    Reading,
    StyleTemplate,
    TargetRanges,
)
from fermon.fermentation.infrastructure.persistence import SqlAlchemyReadingRepository
from tests.fermentation.fakes import InMemoryAlertRepository, InMemoryBatchRepository

pytestmark = pytest.mark.integration

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
CADENCE = timedelta(minutes=15)  # far sparser than the 5 min / 2 min thresholds


async def _feed(
    repository: SqlAlchemyReadingRepository,
    evaluate: EvaluateReadingAlerts,
    slot: int,
    value: float,
) -> None:
    reading = Reading(
        "tank-1",
        "s1",
        MeasurementType.TEMPERATURE,
        value,
        "celsius",
        T0 + slot * CADENCE,
    )
    await repository.add(reading)
    await evaluate.execute(reading)


async def test_a_sparse_series_opens_and_resolves_out_of_range_alerts(
    repository: SqlAlchemyReadingRepository,
) -> None:
    batches = InMemoryBatchRepository()
    alerts = InMemoryAlertRepository()
    await batches.add(
        Batch(
            id=UUID(int=1),
            tank_id="tank-1",
            beer_name="Beer",
            style="IPA",
            template=StyleTemplate.CUSTOM,
            targets=TargetRanges(18.0, 21.0, 1.0),
            status=BatchStatus.ACTIVE,
            planned_start=T0,
            created_at=T0,
            started_at=T0,
        )
    )
    evaluate = EvaluateReadingAlerts(repository, batches, alerts, AlertRules())

    await _feed(repository, evaluate, 0, 20.0)
    await _feed(repository, evaluate, 1, 25.0)  # out of range, held 0
    assert await alerts.list() == []

    await _feed(repository, evaluate, 2, 25.0)  # held 15 min >= 5 min
    [alert] = await alerts.list()
    assert alert.status is AlertStatus.OPEN
    assert alert.opened_at == T0 + 2 * CADENCE

    await _feed(repository, evaluate, 3, 20.0)  # in range, held 0
    assert (await alerts.list())[0].status is AlertStatus.OPEN

    await _feed(repository, evaluate, 4, 20.0)  # held 15 min >= 2 min
    assert (await alerts.list())[0].status is AlertStatus.RESOLVED
