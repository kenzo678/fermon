from datetime import UTC, datetime, timedelta

import pytest

from fermon.fermentation.domain import (
    AlertAction,
    AlertRules,
    InvalidAlertError,
    MeasurementType,
    TargetRanges,
    decide_out_of_range,
    is_silent,
    out_of_range,
    target_bounds,
)

T = MeasurementType.TEMPERATURE
P = MeasurementType.PRESSURE
NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
RULES = AlertRules()


def test_default_rules_are_five_two_and_ten_minutes() -> None:
    assert RULES.out_of_range_after == timedelta(minutes=5)
    assert RULES.resolve_after == timedelta(minutes=2)
    assert RULES.silent_after == timedelta(minutes=10)


@pytest.mark.parametrize("field", ["out_of_range_after", "resolve_after", "silent_after"])
def test_rules_reject_non_positive_durations(field: str) -> None:
    with pytest.raises(InvalidAlertError) as exc:
        AlertRules(**{field: timedelta(0)})
    assert exc.value.field == field


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (17.99, "below"),
        (18.0, None),  # the limits themselves are in range
        (19.5, None),
        (21.0, None),
        (21.01, "above"),
    ],
)
def test_temperature_is_checked_against_min_and_max(value: float, expected: str | None) -> None:
    assert out_of_range(value, TargetRanges(18.0, 21.0, 1.0), T) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0.0, None), (1.0, None), (1.01, "above")],
)
def test_pressure_without_a_minimum_only_has_an_upper_bound(
    value: float, expected: str | None
) -> None:
    assert out_of_range(value, TargetRanges(18.0, 21.0, 1.0), P) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0.19, "below"), (0.2, None), (1.0, None), (1.01, "above")],
)
def test_pressure_minimum_is_checked_when_set(value: float, expected: str | None) -> None:
    assert out_of_range(value, TargetRanges(18.0, 21.0, 1.0, 0.2), P) == expected


def test_alcohol_has_no_alert_range() -> None:
    with pytest.raises(InvalidAlertError):
        out_of_range(5.0, TargetRanges(18.0, 21.0, 1.0), MeasurementType.ALCOHOL)


def test_target_bounds_per_measurement() -> None:
    targets = TargetRanges(18.0, 21.0, 1.0, 0.2)
    assert target_bounds(targets, T) == (18.0, 21.0)
    assert target_bounds(targets, P) == (0.2, 1.0)
    assert target_bounds(TargetRanges(18.0, 21.0, 1.0), P) == (None, 1.0)


def minutes(n: float) -> datetime:
    return NOW - timedelta(minutes=n)


@pytest.mark.parametrize(
    ("is_open", "in_range", "streak_minutes", "expected"),
    [
        # Closed: opens once the violation has lasted 5 minutes (inclusive).
        (False, False, 4.99, AlertAction.NONE),
        (False, False, 5.0, AlertAction.OPEN),
        (False, False, 30, AlertAction.OPEN),
        (False, True, 30, AlertAction.NONE),  # in range and nothing open: nothing to do
        # Open: resolves once back in range for 2 minutes (inclusive), not before (hysteresis).
        (True, True, 1.99, AlertAction.NONE),
        (True, True, 2.0, AlertAction.RESOLVE),
        (True, False, 30, AlertAction.NONE),  # still violating: stays open
    ],
)
def test_sustained_decision_table(
    is_open: bool, in_range: bool, streak_minutes: float, expected: AlertAction
) -> None:
    assert (
        decide_out_of_range(
            is_open=is_open,
            in_range=in_range,
            streak_start=minutes(streak_minutes),
            now=NOW,
            rules=RULES,
        )
        == expected
    )


@pytest.mark.parametrize(
    ("idle_seconds", "expected"),
    [(599, False), (600, True), (601, True)],
)
def test_silence_threshold_is_inclusive(idle_seconds: int, expected: bool) -> None:
    assert is_silent(NOW - timedelta(seconds=idle_seconds), NOW, RULES) is expected
