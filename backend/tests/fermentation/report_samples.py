"""A ready-made finished-batch report for the renderer and API tests."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fermon.fermentation.domain import (
    AggregatedPoint,
    Alert,
    AlertKind,
    AlertStatus,
    Batch,
    BatchReport,
    BatchStatus,
    LabAnalysis,
    LabResult,
    MeasurementType,
    QualityParameter,
    QualityStage,
    QualityStatus,
    StyleTemplate,
    TargetRanges,
    build_batch_report,
)

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
GENERATED_AT = datetime(2026, 1, 9, 8, 30, tzinfo=UTC)
TEMP, PRESSURE, ABV = (
    MeasurementType.TEMPERATURE,
    MeasurementType.PRESSURE,
    MeasurementType.ALCOHOL,
)


def sample_points(hours: int = 48) -> list[AggregatedPoint]:
    """One point every 30 minutes: temperature drifting out of range once, ABV rising."""
    points = []
    for step in range(hours * 2):
        at = T0 + timedelta(minutes=30 * step)
        temperature = 19.0 + (3.5 if 20 <= step < 24 else 0.0) + (step % 4) * 0.2
        points.append(
            AggregatedPoint(at, TEMP, temperature, temperature - 0.1, temperature + 0.1, 30)
        )
        points.append(AggregatedPoint(at, PRESSURE, 0.6, 0.55, 0.65, 30))
        points.append(AggregatedPoint(at, ABV, step * 0.05, step * 0.05, step * 0.05, 30))
    return points


def sample_batch(
    beer_name: str = "Pale Ale", status: BatchStatus = BatchStatus.FINISHED, hours: int = 48
) -> Batch:
    return Batch(
        id=UUID(int=1),
        tank_id="tank-1",
        beer_name=beer_name,
        style="APA",
        template=StyleTemplate.ALE,
        targets=TargetRanges(18.0, 21.0, 1.0, None, 5.0),
        status=status,
        planned_start=T0 - timedelta(days=1),
        created_at=T0 - timedelta(days=2),
        expected_end=T0 + timedelta(days=10),
        started_at=T0,
        finished_at=T0 + timedelta(hours=hours) if status is BatchStatus.FINISHED else None,
    )


def sample_report(
    beer_name: str = "Pale Ale", status: BatchStatus = BatchStatus.FINISHED, hours: int = 48
) -> BatchReport:
    batch = sample_batch(beer_name, status, hours)
    alert = Alert(
        id=UUID(int=70),
        tank_id="tank-1",
        batch_id=batch.id,
        kind=AlertKind.OUT_OF_RANGE,
        measurement=TEMP,
        status=AlertStatus.RESOLVED,
        opened_at=T0 + timedelta(hours=10),
        acknowledged_at=T0 + timedelta(hours=10, minutes=5),
        resolved_at=T0 + timedelta(hours=12),
    )
    analysis = LabAnalysis(
        id=UUID(int=80),
        batch_id=batch.id,
        stage=QualityStage.MATURATION,
        sampled_at=T0 + timedelta(hours=40),
        created_at=T0 + timedelta(hours=41),
        results=(
            LabResult(QualityParameter.PH, 4.4, QualityStatus.WARNING),
            LabResult(QualityParameter.COLOR, 12.0, QualityStatus.IN_SPEC),
        ),
        analyst="Ana",
    )
    return build_batch_report(
        batch=batch,
        profile_name="Pale lager",
        points=sample_points(hours),
        alerts=[alert],
        analyses=[analysis],
        generated_at=GENERATED_AT,
    )
