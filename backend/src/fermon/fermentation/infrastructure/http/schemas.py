from collections.abc import Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from fermon.fermentation.application import TankOverview
from fermon.fermentation.domain import (
    AggregatedPoint,
    AggregationBucket,
    Alert,
    Batch,
    MeasurementType,
    Reading,
    StyleTemplate,
    TargetRanges,
)


class ReadingIn(BaseModel):
    """Inbound reading. Types stay primitive: domain rules are enforced by the domain."""

    model_config = ConfigDict(extra="forbid")

    tank_id: str
    sensor_id: str
    measurement: str
    value: float
    unit: str
    recorded_at: AwareDatetime


class ReadingOut(BaseModel):
    """Outbound reading. Timestamps are always normalized to UTC."""

    tank_id: str
    sensor_id: str
    measurement: str
    value: float
    unit: str
    recorded_at: AwareDatetime

    @classmethod
    def from_domain(cls, reading: Reading) -> "ReadingOut":
        return cls(
            tank_id=reading.tank_id,
            sensor_id=reading.sensor_id,
            measurement=reading.measurement.value,
            value=reading.value,
            unit=reading.unit,
            recorded_at=reading.recorded_at.astimezone(UTC),
        )


class LatestReadingsOut(BaseModel):
    """The newest reading of each measurement; null when the tank never reported it."""

    temperature: ReadingOut | None
    pressure: ReadingOut | None
    alcohol: ReadingOut | None


class TargetRangesIn(BaseModel):
    """Partial target ranges: on create they override the template, on PATCH the current ones."""

    model_config = ConfigDict(extra="forbid")

    temperature_min: float | None = None
    temperature_max: float | None = None
    pressure_max: float | None = None
    pressure_min: float | None = None
    expected_final_abv: float | None = None


class TargetRangesOut(BaseModel):
    temperature_min: float
    temperature_max: float
    pressure_max: float
    pressure_min: float | None
    expected_final_abv: float | None

    @classmethod
    def from_domain(cls, targets: TargetRanges) -> "TargetRangesOut":
        return cls(**asdict(targets))


class BatchTemplateOut(BaseModel):
    template: str
    targets: TargetRangesOut

    @classmethod
    def from_domain(cls, template: StyleTemplate, targets: TargetRanges) -> "BatchTemplateOut":
        return cls(template=template.value, targets=TargetRangesOut.from_domain(targets))


class BatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tank_id: str
    beer_name: str
    style: str
    template: StyleTemplate = StyleTemplate.CUSTOM
    targets: TargetRangesIn | None = None
    planned_start: AwareDatetime | None = None
    expected_end: AwareDatetime | None = None
    notes: str | None = None


class BatchPatch(BaseModel):
    """Fields to change; only those sent are applied (null clears the optional ones)."""

    model_config = ConfigDict(extra="forbid")

    beer_name: str | None = None
    style: str | None = None
    template: StyleTemplate | None = None
    targets: TargetRangesIn | None = None
    planned_start: AwareDatetime | None = None
    expected_end: AwareDatetime | None = None
    notes: str | None = None
    version: int | None = Field(
        default=None,
        ge=1,
        description="If sent, the edit applies only while the batch is still at this version.",
    )


def _utc(moment: datetime | None) -> datetime | None:
    return moment.astimezone(UTC) if moment is not None else None


class BatchOut(BaseModel):
    id: UUID
    tank_id: str
    beer_name: str
    style: str
    template: str
    status: str
    targets: TargetRangesOut
    planned_start: AwareDatetime
    expected_end: AwareDatetime | None
    started_at: AwareDatetime | None
    finished_at: AwareDatetime | None
    notes: str | None
    created_at: AwareDatetime
    version: int

    @classmethod
    def from_domain(cls, batch: Batch) -> "BatchOut":
        return cls(
            id=batch.id,
            tank_id=batch.tank_id,
            beer_name=batch.beer_name,
            style=batch.style,
            template=batch.template.value,
            status=batch.status.value,
            targets=TargetRangesOut.from_domain(batch.targets),
            planned_start=batch.planned_start.astimezone(UTC),
            expected_end=_utc(batch.expected_end),
            started_at=_utc(batch.started_at),
            finished_at=_utc(batch.finished_at),
            notes=batch.notes,
            created_at=batch.created_at.astimezone(UTC),
            version=batch.version,
        )


class ActiveBatchOut(BaseModel):
    """The slice of an active batch a tank card needs."""

    id: UUID
    beer_name: str
    style: str
    targets: TargetRangesOut
    started_at: AwareDatetime
    expected_end: AwareDatetime | None

    @classmethod
    def from_domain(cls, batch: Batch) -> "ActiveBatchOut":
        assert batch.started_at is not None  # active batches have started (domain invariant)
        return cls(
            id=batch.id,
            beer_name=batch.beer_name,
            style=batch.style,
            targets=TargetRangesOut.from_domain(batch.targets),
            started_at=batch.started_at.astimezone(UTC),
            expected_end=_utc(batch.expected_end),
        )


class AlertOut(BaseModel):
    id: UUID
    tank_id: str
    batch_id: UUID
    kind: str
    measurement: str | None
    status: str
    opened_at: AwareDatetime
    acknowledged_at: AwareDatetime | None
    resolved_at: AwareDatetime | None
    details: dict[str, Any]
    version: int

    @classmethod
    def from_domain(cls, alert: Alert) -> "AlertOut":
        return cls(
            id=alert.id,
            tank_id=alert.tank_id,
            batch_id=alert.batch_id,
            kind=alert.kind.value,
            measurement=alert.measurement.value if alert.measurement else None,
            status=alert.status.value,
            opened_at=alert.opened_at.astimezone(UTC),
            acknowledged_at=_utc(alert.acknowledged_at),
            resolved_at=_utc(alert.resolved_at),
            details=alert.details,
            version=alert.version,
        )


class AcknowledgeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int | None = Field(
        default=None,
        ge=1,
        description="If sent, the acknowledgement applies only while the alert is at this version.",
    )


class AlertEventOut(BaseModel):
    """One message of the ``/ws/alerts`` stream: the alert as it is after the change."""

    type: Literal["alert"] = "alert"
    alert: AlertOut


class TankOut(BaseModel):
    id: str
    display_name: str | None
    first_seen_at: AwareDatetime
    active_batch: ActiveBatchOut | None
    open_alerts: int
    latest: LatestReadingsOut

    @classmethod
    def from_domain(cls, overview: TankOverview) -> "TankOut":
        def newest(measurement: MeasurementType) -> ReadingOut | None:
            reading = overview.latest.get(measurement)
            return ReadingOut.from_domain(reading) if reading is not None else None

        return cls(
            id=overview.tank.id,
            display_name=overview.tank.display_name,
            first_seen_at=overview.tank.first_seen_at.astimezone(UTC),
            active_batch=(
                ActiveBatchOut.from_domain(overview.active_batch)
                if overview.active_batch is not None
                else None
            ),
            open_alerts=overview.open_alerts,
            latest=LatestReadingsOut(
                temperature=newest(MeasurementType.TEMPERATURE),
                pressure=newest(MeasurementType.PRESSURE),
                alcohol=newest(MeasurementType.ALCOHOL),
            ),
        )


class AggregatedPointOut(BaseModel):
    bucket_start: AwareDatetime
    avg: float
    min: float
    max: float
    count: int


class AggregatedReadingsOut(BaseModel):
    """Aggregated points per requested measurement (empty list when it has none)."""

    tank_id: str
    bucket: str
    series: dict[str, list[AggregatedPointOut]]

    @classmethod
    def from_domain(
        cls,
        tank_id: str,
        bucket: AggregationBucket,
        measurements: Sequence[MeasurementType],
        points: Sequence[AggregatedPoint],
    ) -> "AggregatedReadingsOut":
        series: dict[str, list[AggregatedPointOut]] = {m.value: [] for m in measurements}
        for p in points:
            series[p.measurement.value].append(
                AggregatedPointOut(
                    bucket_start=p.bucket_start.astimezone(UTC),
                    avg=p.avg,
                    min=p.min,
                    max=p.max,
                    count=p.count,
                )
            )
        return cls(tank_id=tank_id, bucket=bucket.value, series=series)


class ErrorDetail(BaseModel):
    field: str | None
    message: str


class ErrorResponse(BaseModel):
    detail: list[ErrorDetail]
