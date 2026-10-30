import json
from datetime import UTC, datetime

import pytest

from fermon_simulator.messages import UNITS, Reading, build_message

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def test_topic_and_payload_match_contract() -> None:
    reading = Reading("tank-1-temp", "temperature", 18.5, NOW)
    topic, payload = build_message("tank-1", reading)
    assert topic == "fermon/tanks/tank-1/readings"
    assert isinstance(payload, bytes)
    body = json.loads(payload)
    assert set(body) == {"sensor_id", "measurement", "value", "unit", "recorded_at"}
    assert body["sensor_id"] == "tank-1-temp"
    assert body["measurement"] == "temperature"
    assert body["value"] == 18.5
    assert isinstance(body["value"], float)
    assert body["unit"] == "celsius"


@pytest.mark.parametrize(
    ("measurement", "unit"),
    [("temperature", "celsius"), ("pressure", "bar"), ("alcohol", "percent_abv")],
)
def test_units_per_measurement(measurement: str, unit: str) -> None:
    assert UNITS[measurement] == unit
    _, payload = build_message("t", Reading("s", measurement, 1.0, NOW))  # type: ignore[arg-type]
    assert json.loads(payload)["unit"] == unit


def test_recorded_at_is_tz_aware_iso8601() -> None:
    _, payload = build_message("t", Reading("s", "pressure", 0.3, NOW))
    parsed = datetime.fromisoformat(json.loads(payload)["recorded_at"])
    assert parsed.tzinfo is not None
    assert parsed.utcoffset().total_seconds() == 0  # type: ignore[union-attr]
    assert parsed == NOW


def test_naive_datetime_is_rejected() -> None:
    with pytest.raises(ValueError):
        build_message("t", Reading("s", "pressure", 0.3, datetime(2026, 1, 1)))  # noqa: DTZ001
