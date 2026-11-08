import math
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from fermon.fermentation.domain.errors import (
    InvalidBatchError,
    InvalidBatchTransitionError,
    InvalidIdentifierError,
)
from fermon.fermentation.domain.identifier import normalize_id
from fermon.fermentation.domain.measurement import MeasurementType


class BatchStatus(StrEnum):
    PLANNED = "planned"
    ACTIVE = "active"
    FINISHED = "finished"


class StyleTemplate(StrEnum):
    ALE = "ale"
    LAGER = "lager"
    CUSTOM = "custom"  # no preset: targets are entered by hand


def _number(field: str, value: object, limits: tuple[float, float]) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise InvalidBatchError(field, "must be a real number")
    if not math.isfinite(value):
        raise InvalidBatchError(field, "must be a finite number")
    low, high = limits
    if not low <= value <= high:
        raise InvalidBatchError(field, f"{value} is outside {low}..{high}")
    return float(value)


@dataclass(frozen=True, slots=True)
class TargetRanges:
    """Desired fermentation ranges of a batch, in the canonical units of each measurement."""

    temperature_min: float
    temperature_max: float
    pressure_max: float
    pressure_min: float | None = None
    expected_final_abv: float | None = None

    def __post_init__(self) -> None:
        temperature = MeasurementType.TEMPERATURE.limits
        pressure = MeasurementType.PRESSURE.limits
        values = {
            "temperature_min": _number("temperature_min", self.temperature_min, temperature),
            "temperature_max": _number("temperature_max", self.temperature_max, temperature),
            "pressure_max": _number("pressure_max", self.pressure_max, pressure),
        }
        if values["temperature_min"] >= values["temperature_max"]:
            raise InvalidBatchError("temperature_max", "must be greater than temperature_min")
        if self.pressure_min is not None:
            values["pressure_min"] = _number("pressure_min", self.pressure_min, pressure)
            if values["pressure_min"] >= values["pressure_max"]:
                raise InvalidBatchError("pressure_min", "must be lower than pressure_max")
        if self.expected_final_abv is not None:
            values["expected_final_abv"] = _number(
                "expected_final_abv", self.expected_final_abv, MeasurementType.ALCOHOL.limits
            )
        for field, value in values.items():
            object.__setattr__(self, field, value)


_TEMPLATES: dict[StyleTemplate, TargetRanges] = {
    StyleTemplate.ALE: TargetRanges(18.0, 21.0, 1.0, None, 5.0),
    StyleTemplate.LAGER: TargetRanges(8.0, 12.0, 1.2, None, 5.2),
}


def template_targets(template: StyleTemplate) -> TargetRanges | None:
    """The preset ranges of a style template; None for ``custom``."""
    return _TEMPLATES.get(template)


def _aware(field: str, value: object) -> datetime:
    if not isinstance(value, datetime):
        raise InvalidBatchError(field, "must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise InvalidBatchError(field, "must be timezone-aware")
    return value


def _required_text(field: str, value: object) -> str:
    try:
        return normalize_id(field, value)
    except InvalidIdentifierError as error:
        raise InvalidBatchError(error.field, error.reason) from None


_EDITABLE = frozenset(
    {"beer_name", "style", "template", "targets", "planned_start", "expected_end", "notes"}
)


@dataclass(frozen=True, slots=True)
class Batch:
    """A beer fermenting (or about to) in one tank: planned -> active -> finished."""

    id: UUID
    tank_id: str
    beer_name: str
    style: str
    template: StyleTemplate
    targets: TargetRanges
    status: BatchStatus
    planned_start: datetime
    created_at: datetime
    expected_end: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    notes: str | None = None
    version: int = 1  # optimistic-concurrency token: +1 on every transition or edit

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID):
            raise InvalidBatchError("id", "must be a UUID")
        object.__setattr__(self, "tank_id", _required_text("tank_id", self.tank_id))
        object.__setattr__(self, "beer_name", _required_text("beer_name", self.beer_name))
        object.__setattr__(self, "style", _required_text("style", self.style))
        try:
            object.__setattr__(self, "template", StyleTemplate(self.template))
        except ValueError:
            raise InvalidBatchError("template", "must be one of ale, lager, custom") from None
        try:
            object.__setattr__(self, "status", BatchStatus(self.status))
        except ValueError:
            raise InvalidBatchError("status", "must be planned, active or finished") from None
        if not isinstance(self.targets, TargetRanges):
            raise InvalidBatchError("targets", "must be TargetRanges")
        _aware("planned_start", self.planned_start)
        _aware("created_at", self.created_at)
        if self.expected_end is not None:
            _aware("expected_end", self.expected_end)
            if self.expected_end <= self.planned_start:
                raise InvalidBatchError("expected_end", "must be after planned_start")
        for field in ("started_at", "finished_at"):
            if getattr(self, field) is not None:
                _aware(field, getattr(self, field))
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise InvalidBatchError("version", "must be an integer >= 1")
        self._check_lifecycle()

    def _check_lifecycle(self) -> None:
        planned = self.status is BatchStatus.PLANNED
        finished = self.status is BatchStatus.FINISHED
        if planned and self.started_at is not None:
            raise InvalidBatchError("started_at", "a planned batch has not started")
        if not planned and self.started_at is None:
            raise InvalidBatchError("started_at", f"a {self.status.value} batch must have started")
        if finished and self.finished_at is None:
            raise InvalidBatchError("finished_at", "a finished batch must have finished")
        if not finished and self.finished_at is not None:
            raise InvalidBatchError("finished_at", f"a {self.status.value} batch has not finished")

    def start(self, now: datetime) -> "Batch":
        if self.status is not BatchStatus.PLANNED:
            raise InvalidBatchTransitionError(str(self.id), self.status.value, "start")
        _aware("started_at", now)
        return replace(self, status=BatchStatus.ACTIVE, started_at=now, version=self.version + 1)

    def finish(self, now: datetime) -> "Batch":
        if self.status is not BatchStatus.ACTIVE:
            raise InvalidBatchTransitionError(str(self.id), self.status.value, "finish")
        _aware("finished_at", now)
        return replace(self, status=BatchStatus.FINISHED, finished_at=now, version=self.version + 1)

    def edit(self, **changes: Any) -> "Batch":
        """A copy with the given editable fields replaced (and revalidated)."""
        if self.status is BatchStatus.FINISHED:
            raise InvalidBatchTransitionError(str(self.id), self.status.value, "edit")
        for field in changes:
            if field not in _EDITABLE:
                raise InvalidBatchError(field, "cannot be edited")
        return replace(self, **changes, version=self.version + 1)
