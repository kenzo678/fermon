from collections.abc import Sequence
from datetime import UTC

from pydantic import AwareDatetime, BaseModel, ConfigDict

from fermon.fermentation.application import TankOverview
from fermon.fermentation.domain import (
    AggregatedPoint,
    AggregationBucket,
    MeasurementType,
    Reading,
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


class TankOut(BaseModel):
    id: str
    display_name: str | None
    first_seen_at: AwareDatetime
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
