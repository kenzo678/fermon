"""Wire format of the ``fermon_readings`` NOTIFY channel (the same shape the API serves)."""

import json
from datetime import UTC

from pydantic import AwareDatetime, BaseModel, ConfigDict, ValidationError

from fermon.fermentation.domain import DomainError, MeasurementType, Reading

# PostgreSQL channel carrying one message per newly stored reading. NOTIFY payloads are limited
# to 8000 bytes; a reading with generous identifiers is a few hundred.
READINGS_CHANNEL = "fermon_readings"


class InvalidPayloadError(ValueError):
    """A NOTIFY payload that is not a valid reading."""


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
