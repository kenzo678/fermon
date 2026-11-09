"""Wire format of the ``fermon_readings`` and ``fermon_alerts`` NOTIFY channels (the API shape)."""

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, ValidationError

from fermon.fermentation.domain import (
    Alert,
    AlertKind,
    AlertStatus,
    DomainError,
    MeasurementType,
    Reading,
)

# PostgreSQL channel carrying one message per newly stored reading. NOTIFY payloads are limited
# to 8000 bytes; a reading with generous identifiers is a few hundred.
READINGS_CHANNEL = "fermon_readings"
# One message per stored alert revision (opened, acknowledged, resolved), shaped like AlertOut.
ALERTS_CHANNEL = "fermon_alerts"


class InvalidPayloadError(ValueError):
    """A NOTIFY payload that is not a valid reading or alert."""


class _ReadingPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tank_id: str
    sensor_id: str
    measurement: MeasurementType
    value: float
    unit: str
    recorded_at: AwareDatetime


def encode_reading(reading: Reading) -> str:
    return json.dumps(
        {
            "tank_id": reading.tank_id,
            "sensor_id": reading.sensor_id,
            "measurement": reading.measurement.value,
            "value": reading.value,
            "unit": reading.unit,
            "recorded_at": reading.recorded_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        },
        separators=(",", ":"),
    )


def decode_reading(payload: str) -> Reading:
    try:
        parsed = _ReadingPayload.model_validate_json(payload)
        return Reading(**dict(parsed))
    except (ValidationError, DomainError) as exc:
        raise InvalidPayloadError(str(exc)) from exc


class _AlertPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    tank_id: str
    batch_id: UUID
    kind: AlertKind
    measurement: MeasurementType | None
    status: AlertStatus
    opened_at: AwareDatetime
    acknowledged_at: AwareDatetime | None
    resolved_at: AwareDatetime | None
    details: dict[str, Any]
    version: int


def _utc(moment: datetime | None) -> str | None:
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z") if moment else None


def encode_alert(alert: Alert) -> str:
    return json.dumps(
        {
            "id": str(alert.id),
            "tank_id": alert.tank_id,
            "batch_id": str(alert.batch_id),
            "kind": alert.kind.value,
            "measurement": alert.measurement.value if alert.measurement else None,
            "status": alert.status.value,
            "opened_at": _utc(alert.opened_at),
            "acknowledged_at": _utc(alert.acknowledged_at),
            "resolved_at": _utc(alert.resolved_at),
            "details": alert.details,
            "version": alert.version,
        },
        separators=(",", ":"),
    )


def decode_alert(payload: str) -> Alert:
    try:
        parsed = _AlertPayload.model_validate_json(payload)
        return Alert(**dict(parsed))
    except (ValidationError, DomainError) as exc:
        raise InvalidPayloadError(str(exc)) from exc
