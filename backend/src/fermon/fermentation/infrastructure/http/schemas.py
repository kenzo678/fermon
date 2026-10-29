from datetime import UTC

from pydantic import AwareDatetime, BaseModel, ConfigDict

from fermon.fermentation.domain import Reading


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


class ErrorDetail(BaseModel):
    field: str | None
    message: str


class ErrorResponse(BaseModel):
    detail: list[ErrorDetail]
