from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest

from fermon.fermentation.domain import (
    Alert,
    AlertKind,
    AlertStatus,
    InvalidAlertError,
    InvalidAlertTransitionError,
    MeasurementType,
)

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
LATER = T0 + timedelta(minutes=3)


def make_alert(**overrides: Any) -> Alert:
    values: dict[str, Any] = {
        "id": UUID(int=1),
        "tank_id": "tank-1",
        "batch_id": UUID(int=2),
        "kind": AlertKind.OUT_OF_RANGE,
        "measurement": MeasurementType.TEMPERATURE,
        "status": AlertStatus.OPEN,
        "opened_at": T0,
        "details": {"observed": 25.0, "bound": "above", "target_min": 18.0, "target_max": 21.0},
    }
    return Alert(**{**values, **overrides})


def test_a_new_alert_is_open_with_version_one() -> None:
    alert = make_alert()
    assert alert.status is AlertStatus.OPEN and alert.version == 1
    assert alert.acknowledged_at is None and alert.resolved_at is None


def test_acknowledge_moves_open_to_acknowledged_and_bumps_the_version() -> None:
    acked = make_alert().acknowledge(LATER)
    assert acked.status is AlertStatus.ACKNOWLEDGED
    assert acked.acknowledged_at == LATER and acked.version == 2


def test_resolve_works_from_open_and_from_acknowledged() -> None:
    from_open = make_alert().resolve(LATER)
    from_acked = make_alert().acknowledge(T0).resolve(LATER)
    for resolved in (from_open, from_acked):
        assert resolved.status is AlertStatus.RESOLVED and resolved.resolved_at == LATER
    assert from_open.acknowledged_at is None
    assert from_acked.acknowledged_at == T0  # who acknowledged it first is kept


@pytest.mark.parametrize(
    ("status", "action"),
    [
        (AlertStatus.ACKNOWLEDGED, "acknowledge"),
        (AlertStatus.RESOLVED, "acknowledge"),
        (AlertStatus.RESOLVED, "resolve"),
    ],
)
def test_invalid_transitions_are_rejected(status: AlertStatus, action: str) -> None:
    alert = make_alert(
        status=status,
        acknowledged_at=T0 if status is not AlertStatus.OPEN else None,
        resolved_at=T0 if status is AlertStatus.RESOLVED else None,
    )
    with pytest.raises(InvalidAlertTransitionError) as exc:
        getattr(alert, action)(LATER)
    assert exc.value.action == action and exc.value.status == status.value


def test_silent_sensor_alert_has_no_measurement() -> None:
    alert = make_alert(
        kind=AlertKind.SILENT_SENSOR, measurement=None, details={"last_reading_at": None}
    )
    assert alert.measurement is None


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"measurement": None}, "measurement"),  # out_of_range needs one
        ({"measurement": MeasurementType.ALCOHOL}, "measurement"),
        ({"kind": AlertKind.SILENT_SENSOR}, "measurement"),  # silent must not have one
        ({"kind": "bogus"}, "kind"),
        ({"status": "bogus"}, "status"),
        ({"id": "not-a-uuid"}, "id"),
        ({"opened_at": datetime(2026, 1, 1)}, "opened_at"),
        ({"version": 0}, "version"),
        ({"status": AlertStatus.RESOLVED}, "resolved_at"),
        ({"resolved_at": T0}, "resolved_at"),
        ({"status": AlertStatus.ACKNOWLEDGED}, "acknowledged_at"),
        ({"tank_id": " "}, "tank_id"),
    ],
)
def test_invariants_are_enforced(overrides: dict[str, Any], field: str) -> None:
    with pytest.raises(InvalidAlertError) as exc:
        make_alert(**overrides)
    assert exc.value.field == field


def test_resolving_or_acknowledging_before_the_alert_opened_is_rejected() -> None:
    before = T0 - timedelta(seconds=1)
    with pytest.raises(InvalidAlertError) as resolve_error:
        make_alert().resolve(before)
    assert resolve_error.value.field == "resolved_at"
    with pytest.raises(InvalidAlertError) as ack_error:
        make_alert().acknowledge(before)
    assert ack_error.value.field == "acknowledged_at"
    assert make_alert().resolve(T0).resolved_at == T0  # the same instant is fine


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"status": AlertStatus.RESOLVED, "resolved_at": T0 - timedelta(minutes=1)}, "resolved_at"),
        (
            {"status": AlertStatus.ACKNOWLEDGED, "acknowledged_at": T0 - timedelta(minutes=1)},
            "acknowledged_at",
        ),
    ],
)
def test_stored_timestamps_cannot_precede_opened_at(overrides: dict[str, Any], field: str) -> None:
    with pytest.raises(InvalidAlertError) as exc:
        make_alert(**overrides)
    assert exc.value.field == field
