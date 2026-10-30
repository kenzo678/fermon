from datetime import UTC, datetime, timedelta, timezone

import pytest

from fermon.fermentation.domain import MeasurementType, Reading
from fermon.fermentation.infrastructure.realtime.payload import (
    READINGS_CHANNEL,
    InvalidPayloadError,
    decode_reading,
    encode_reading,
)

READING = Reading(
    "tank-1",
    "s1",
    MeasurementType.TEMPERATURE,
    18.5,
    "celsius",
    datetime(2026, 1, 1, 12, 0, tzinfo=timezone(timedelta(hours=-3))),
)


def test_channel_name_is_stable() -> None:
    assert READINGS_CHANNEL == "fermon_readings"


def test_encode_uses_the_api_shape_with_utc_timestamp() -> None:
    import json

    assert json.loads(encode_reading(READING)) == {
        "tank_id": "tank-1",
        "sensor_id": "s1",
        "measurement": "temperature",
        "value": 18.5,
        "unit": "celsius",
        "recorded_at": "2026-01-01T15:00:00Z",
    }


def test_encoded_payload_is_far_below_the_notify_limit() -> None:
    long_reading = Reading(
        "t" * 200, "s" * 200, MeasurementType.PRESSURE, 1.0, "bar", datetime(2026, 1, 1, tzinfo=UTC)
    )

    assert len(encode_reading(long_reading).encode()) < 1000


def test_decode_round_trips_to_an_equal_instant() -> None:
    decoded = decode_reading(encode_reading(READING))

    assert decoded == READING
    assert decoded.recorded_at.utcoffset() == timedelta(0)


@pytest.mark.parametrize(
    "payload",
    [
        "not json",
        "[]",
        "{}",
        '{"tank_id": "t"}',
        '{"tank_id":"t","sensor_id":"s","measurement":"nope","value":1,"unit":"x",'
        '"recorded_at":"2026-01-01T00:00:00Z"}',
        '{"tank_id":"t","sensor_id":"s","measurement":"pressure","value":1,"unit":"bar",'
        '"recorded_at":"2026-01-01T00:00:00"}',
    ],
)
def test_decode_rejects_malformed_payloads(payload: str) -> None:
    with pytest.raises(InvalidPayloadError):
        decode_reading(payload)
