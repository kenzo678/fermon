"""Pure alert rules: no I/O and no clock, so every boundary is unit-testable.

Boundary decisions (all documented here once):

* A value equal to a target limit is IN range; only strictly beyond a limit violates it.
* A duration threshold is met when it is reached (``>=``), not only exceeded.
* Time is measured on the readings' ``recorded_at``, never on arrival time.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Literal

from fermon.fermentation.domain.alert import ALERTABLE_MEASUREMENTS
from fermon.fermentation.domain.batch import TargetRanges
from fermon.fermentation.domain.errors import InvalidAlertError
from fermon.fermentation.domain.measurement import MeasurementType

Bound = Literal["below", "above"]


@dataclass(frozen=True, slots=True)
class AlertRules:
    out_of_range_after: timedelta = timedelta(minutes=5)  # violation held this long -> open
    resolve_after: timedelta = timedelta(minutes=2)  # back in range this long -> resolve
    silent_after: timedelta = timedelta(minutes=10)  # no reading this long -> silent sensor

    def __post_init__(self) -> None:
        for name in ("out_of_range_after", "resolve_after", "silent_after"):
            if getattr(self, name) <= timedelta(0):
                raise InvalidAlertError(name, "must be positive")


class AlertAction(StrEnum):
    NONE = "none"
    OPEN = "open"
    RESOLVE = "resolve"


def target_bounds(
    targets: TargetRanges, measurement: MeasurementType
) -> tuple[float | None, float | None]:
    """(low, high) limits of a measurement; ``None`` means unbounded on that side."""
    if measurement is MeasurementType.TEMPERATURE:
        return targets.temperature_min, targets.temperature_max
    if measurement is MeasurementType.PRESSURE:
        return targets.pressure_min, targets.pressure_max
    raise InvalidAlertError("measurement", f"{measurement.value} has no alert range")


def out_of_range(value: float, targets: TargetRanges, measurement: MeasurementType) -> Bound | None:
    """Which limit the value violates, or ``None`` when it is within the target range."""
    if measurement not in ALERTABLE_MEASUREMENTS:
        raise InvalidAlertError("measurement", f"{measurement.value} has no alert range")
    low, high = target_bounds(targets, measurement)
    if low is not None and value < low:
        return "below"
    if high is not None and value > high:
        return "above"
    return None


def decide_out_of_range(
    *, is_open: bool, in_range: bool, streak_start: datetime, now: datetime, rules: AlertRules
) -> AlertAction:
    """The sustained-violation rule with hysteresis.

    ``in_range`` is the latest reading's state and ``streak_start`` when that state began
    (the earliest reading of the uninterrupted run it belongs to). Opening needs the violation
    to last ``out_of_range_after``; resolving needs the recovery to last ``resolve_after``, so a
    value flapping around a limit neither opens nor closes alerts by itself.
    """
    held = now - streak_start
    if not is_open and not in_range and held >= rules.out_of_range_after:
        return AlertAction.OPEN
    if is_open and in_range and held >= rules.resolve_after:
        return AlertAction.RESOLVE
    return AlertAction.NONE


def is_silent(last_activity: datetime, now: datetime, rules: AlertRules) -> bool:
    """Whether a tank has reported nothing since ``last_activity`` for the silence threshold."""
    return now - last_activity >= rules.silent_after
