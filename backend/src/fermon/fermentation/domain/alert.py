from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from fermon.fermentation.domain.errors import (
    InvalidAlertError,
    InvalidAlertTransitionError,
    InvalidIdentifierError,
)
from fermon.fermentation.domain.identifier import normalize_id
from fermon.fermentation.domain.measurement import MeasurementType


class AlertKind(StrEnum):
    OUT_OF_RANGE = "out_of_range"
    SILENT_SENSOR = "silent_sensor"


class AlertStatus(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


# Measurements that have target ranges to alert on (alcohol only shows progress).
ALERTABLE_MEASUREMENTS = (MeasurementType.TEMPERATURE, MeasurementType.PRESSURE)


def _aware(name: str, value: object) -> datetime:
    if not isinstance(value, datetime):
        raise InvalidAlertError(name, "must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise InvalidAlertError(name, "must be timezone-aware")
    return value


@dataclass(frozen=True, slots=True)
class Alert:
    """Something that needs attention in a tank: open -> acknowledged -> resolved.

    ``details`` is a JSON-friendly snapshot taken when the alert opened. For ``out_of_range``:
    ``observed`` (value that completed the sustained violation), ``bound`` ("below"/"above"),
    ``target_min`` and ``target_max`` (``None`` when unbounded). For ``silent_sensor``:
    ``last_reading_at`` (ISO 8601, or ``None`` if the tank sent nothing since the batch started).
    """

    id: UUID
    tank_id: str
    batch_id: UUID
    kind: AlertKind
    measurement: MeasurementType | None
    status: AlertStatus
    opened_at: datetime
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None
    details: dict[str, Any] = field(default_factory=dict)
    version: int = 1  # optimistic-concurrency token: +1 on every transition

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID):
            raise InvalidAlertError("id", "must be a UUID")
        if not isinstance(self.batch_id, UUID):
            raise InvalidAlertError("batch_id", "must be a UUID")
        try:
            object.__setattr__(self, "tank_id", normalize_id("tank_id", self.tank_id))
        except InvalidIdentifierError as error:
            raise InvalidAlertError(error.field, error.reason) from None
        try:
            object.__setattr__(self, "kind", AlertKind(self.kind))
        except ValueError:
            raise InvalidAlertError("kind", "must be out_of_range or silent_sensor") from None
        try:
            object.__setattr__(self, "status", AlertStatus(self.status))
        except ValueError:
            raise InvalidAlertError("status", "must be open, acknowledged or resolved") from None
        self._check_measurement()
        _aware("opened_at", self.opened_at)
        for name in ("acknowledged_at", "resolved_at"):
            if getattr(self, name) is not None:
                _aware(name, getattr(self, name))
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise InvalidAlertError("version", "must be an integer >= 1")
        self._check_lifecycle()

    def _check_measurement(self) -> None:
        if self.kind is AlertKind.SILENT_SENSOR:
            if self.measurement is not None:
                raise InvalidAlertError("measurement", "a silent_sensor alert has none")
        elif self.measurement not in ALERTABLE_MEASUREMENTS:
            raise InvalidAlertError(
                "measurement", "an out_of_range alert needs temperature or pressure"
            )

    def _check_lifecycle(self) -> None:
        resolved = self.status is AlertStatus.RESOLVED
        if resolved and self.resolved_at is None:
            raise InvalidAlertError("resolved_at", "a resolved alert must have been resolved")
        if not resolved and self.resolved_at is not None:
            raise InvalidAlertError("resolved_at", f"a {self.status.value} alert is not resolved")
        if self.status is AlertStatus.ACKNOWLEDGED and self.acknowledged_at is None:
            raise InvalidAlertError("acknowledged_at", "an acknowledged alert must have a time")
        for name in ("acknowledged_at", "resolved_at"):
            stamp = getattr(self, name)
            if stamp is not None and stamp < self.opened_at:
                raise InvalidAlertError(name, "cannot be earlier than opened_at")

    @property
    def is_unresolved(self) -> bool:
        return self.status is not AlertStatus.RESOLVED

    def acknowledge(self, now: datetime) -> "Alert":
        if self.status is not AlertStatus.OPEN:
            raise InvalidAlertTransitionError(str(self.id), self.status.value, "acknowledge")
        _aware("acknowledged_at", now)
        return replace(
            self, status=AlertStatus.ACKNOWLEDGED, acknowledged_at=now, version=self.version + 1
        )

    def resolve(self, now: datetime) -> "Alert":
        if self.status is AlertStatus.RESOLVED:
            raise InvalidAlertTransitionError(str(self.id), self.status.value, "resolve")
        _aware("resolved_at", now)
        return replace(self, status=AlertStatus.RESOLVED, resolved_at=now, version=self.version + 1)
