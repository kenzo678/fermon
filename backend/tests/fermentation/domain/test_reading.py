import dataclasses
import math
from datetime import UTC, datetime, timedelta, tzinfo
from typing import Any

import pytest

from fermon.fermentation.domain import (
    DomainError,
    InvalidReadingError,
    MeasurementType,
    Reading,
)

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def make(**overrides: Any) -> Reading:
    fields: dict[str, Any] = {
        "tank_id": "tank-1",
        "sensor_id": "sensor-1",
        "measurement": MeasurementType.TEMPERATURE,
        "value": 18.5,
        "unit": "celsius",
        "recorded_at": NOW,
    }
    fields.update(overrides)
    return Reading(**fields)


@pytest.mark.parametrize(
    ("measurement", "unit", "value"),
    [
        (MeasurementType.TEMPERATURE, "celsius", 18.5),
        (MeasurementType.PRESSURE, "bar", 1.2),
        (MeasurementType.ALCOHOL, "percent_abv", 5.0),
    ],
)
def test_valid_reading(measurement: MeasurementType, unit: str, value: float) -> None:
    reading = make(measurement=measurement, unit=unit, value=value)

    assert reading.measurement is measurement
    assert reading.value == value
    assert reading.unit == unit


@pytest.mark.parametrize(
    ("measurement", "unit"),
    [
        (MeasurementType.TEMPERATURE, "celsius"),
        (MeasurementType.PRESSURE, "bar"),
        (MeasurementType.ALCOHOL, "percent_abv"),
    ],
)
def test_canonical_unit_and_limits_inclusive(measurement: MeasurementType, unit: str) -> None:
    assert measurement.unit == unit
    low, high = measurement.limits
    assert make(measurement=measurement, unit=unit, value=low).value == low
    assert make(measurement=measurement, unit=unit, value=high).value == high
    for outside in (low - 0.001, high + 0.001):
        with pytest.raises(InvalidReadingError, match="value"):
            make(measurement=measurement, unit=unit, value=outside)


def test_ids_are_stripped() -> None:
    reading = make(tank_id="  tank-9 ", sensor_id=" s-2\n")

    assert reading.tank_id == "tank-9"
    assert reading.sensor_id == "s-2"


@pytest.mark.parametrize("field", ["tank_id", "sensor_id"])
@pytest.mark.parametrize("blank", ["", "   ", "\t\n"])
def test_blank_ids_rejected(field: str, blank: str) -> None:
    with pytest.raises(InvalidReadingError, match=field):
        make(**{field: blank})


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_non_finite_value_rejected(bad: float) -> None:
    with pytest.raises(InvalidReadingError, match="value"):
        make(value=bad)


@pytest.mark.parametrize(
    ("measurement", "unit"),
    [
        (MeasurementType.TEMPERATURE, "fahrenheit"),
        (MeasurementType.TEMPERATURE, "bar"),
        (MeasurementType.PRESSURE, "psi"),
        (MeasurementType.ALCOHOL, "celsius"),
    ],
)
def test_wrong_unit_rejected(measurement: MeasurementType, unit: str) -> None:
    low, _ = measurement.limits
    with pytest.raises(InvalidReadingError, match="unit"):
        make(measurement=measurement, unit=unit, value=low)


def test_naive_datetime_rejected() -> None:
    with pytest.raises(InvalidReadingError, match="recorded_at"):
        make(recorded_at=datetime(2026, 1, 1, 12, 0))


def test_invalid_reading_is_domain_error() -> None:
    assert issubclass(InvalidReadingError, DomainError)


def test_reading_is_immutable() -> None:
    reading = make()

    with pytest.raises(dataclasses.FrozenInstanceError):
        reading.value = 1.0  # type: ignore[misc]


class NoOffsetTz(tzinfo):
    def utcoffset(self, dt: datetime | None) -> timedelta | None:
        return None

    def dst(self, dt: datetime | None) -> timedelta | None:
        return None

    def tzname(self, dt: datetime | None) -> str | None:
        return None


def test_tzinfo_without_offset_rejected() -> None:
    with pytest.raises(InvalidReadingError, match="recorded_at"):
        make(recorded_at=datetime(2026, 1, 1, 12, 0, tzinfo=NoOffsetTz()))


def test_raw_string_measurement_rejected() -> None:
    with pytest.raises(InvalidReadingError) as exc:
        make(measurement="temperature")

    assert exc.value.field == "measurement"


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("tank_id", None),
        ("tank_id", 5),
        ("sensor_id", None),
        ("sensor_id", b"s"),
        ("value", "18.5"),
        ("value", None),
        ("value", True),
        ("recorded_at", "2026-01-01T12:00:00+00:00"),
        ("recorded_at", None),
    ],
)
def test_wrong_types_raise_domain_error(field: str, bad: Any) -> None:
    with pytest.raises(InvalidReadingError) as exc:
        make(**{field: bad})

    assert exc.value.field == field


def test_int_value_accepted() -> None:
    assert make(value=18).value == 18


def test_blank_id_error_message_is_not_duplicated() -> None:
    with pytest.raises(InvalidReadingError) as excinfo:
        make(tank_id="  ")
    assert str(excinfo.value) == "invalid tank_id: must not be blank"
