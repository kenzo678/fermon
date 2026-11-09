"""Alert queries and the operator's acknowledge action (the engine's writes: alerts.py)."""

from collections.abc import Sequence
from uuid import UUID

from fermon.fermentation.application.batches import Clock
from fermon.fermentation.application.ports import AlertRepository
from fermon.fermentation.domain import (
    UNRESOLVED_STATUSES,
    Alert,
    AlertKind,
    AlertNotFoundError,
    AlertStatus,
    ConcurrentAlertUpdateError,
    InvalidAlertError,
    normalize_id,
)

DEFAULT_LIMIT = 100
MAX_LIMIT = 500


class ListAlerts:
    def __init__(self, alerts: AlertRepository) -> None:
        self._alerts = alerts

    async def execute(
        self,
        tank_id: str | None = None,
        batch_id: UUID | None = None,
        statuses: Sequence[AlertStatus] | None = None,
        kind: AlertKind | None = None,
        limit: int = DEFAULT_LIMIT,
    ) -> list[Alert]:
        """Alerts newest first. Without ``statuses`` only the unresolved ones (open and
        acknowledged) are returned: that is what needs attention.
        """
        if isinstance(limit, bool) or not 1 <= limit <= MAX_LIMIT:
            raise InvalidAlertError("limit", f"must be between 1 and {MAX_LIMIT}")
        return await self._alerts.list(
            tank_id=normalize_id("tank_id", tank_id) if tank_id is not None else None,
            statuses=tuple(dict.fromkeys(statuses)) if statuses else UNRESOLVED_STATUSES,
            kind=kind,
            batch_id=batch_id,
            limit=limit,
        )


class GetAlert:
    def __init__(self, alerts: AlertRepository) -> None:
        self._alerts = alerts

    async def execute(self, alert_id: UUID) -> Alert:
        alert = await self._alerts.get(alert_id)
        if alert is None:
            raise AlertNotFoundError(str(alert_id))
        return alert


_MAX_ATTEMPTS = 3


class AcknowledgeAlert:
    def __init__(self, alerts: AlertRepository, clock: Clock) -> None:
        self._alerts = alerts
        self._clock = clock

    async def execute(self, alert_id: UUID, expected_version: int | None = None) -> Alert:
        """open -> acknowledged, stamped with the clock.

        Idempotent: an already acknowledged alert is returned untouched (the caller's goal is
        met, whatever version it saw). A resolved alert raises InvalidAlertTransitionError; a
        stale ``expected_version`` raises ConcurrentAlertUpdateError. Without ``expected_version`` a
        racing write is re-read, so concurrent acknowledges all succeed.
        """
        for _ in range(_MAX_ATTEMPTS):
            alert = await self._alerts.get(alert_id)
            if alert is None:
                raise AlertNotFoundError(str(alert_id))
            if alert.status is AlertStatus.ACKNOWLEDGED:
                return alert
            acknowledged = alert.acknowledge(self._clock())  # raises for a resolved alert
            if expected_version is not None and expected_version != alert.version:
                raise ConcurrentAlertUpdateError(str(alert_id))
            try:
                await self._alerts.update(acknowledged)
            except ConcurrentAlertUpdateError:
                # With if-match the caller asked for exactly that revision: surface the conflict.
                # Without it, re-read: a concurrent acknowledge means the goal is met, and a
                # concurrent resolve surfaces as the real reason (invalid transition).
                if expected_version is not None:
                    raise
                continue
            return acknowledged
        raise ConcurrentAlertUpdateError(str(alert_id))
