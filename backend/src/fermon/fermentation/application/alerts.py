"""Alert engine use cases: evaluate readings as they arrive and check for silent sensors.

State is derived from stored readings and the single unresolved alert per (tank, kind,
measurement), never from in-process memory. A missed evaluation (outage, crash) therefore heals
on the next reading or the next periodic check, and any number of ingestors/API workers can run.
"""

import logging
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from uuid import UUID, uuid4

from fermon.fermentation.application.batches import Clock
from fermon.fermentation.application.ports import (
    AlertRepository,
    BatchRepository,
    ReadingRepository,
)
from fermon.fermentation.domain import (
    ALERTABLE_MEASUREMENTS,
    Alert,
    AlertAction,
    AlertKind,
    AlertRules,
    AlertStatus,
    Batch,
    BatchStatus,
    ConcurrentAlertUpdateError,
    Reading,
    decide_out_of_range,
    is_silent,
    out_of_range,
    target_bounds,
)

logger = logging.getLogger(__name__)

_RESOLVE_ATTEMPTS = 3


BATCH_FINISHED = "batch_finished"
"""``details["resolution"]`` of alerts closed because their batch is no longer active."""

LATE_DATA = "late_data"
"""``details["resolution"]`` of a silent alert closed by a reading recorded before it opened.

Normal recovery (a reading after the alert opened) leaves ``details`` untouched."""


def _proves_recovery(alert: Alert, reading: Reading) -> bool:
    """A reading resolves a silent alert only if newer than the evidence the alert was based on.

    That evidence is ``details["last_reading_at"]`` (absent/``None``: the tank had sent nothing, so
    any reading of the batch qualifies). Older or equal readings (broker backlog) prove nothing new.
    """
    last = alert.details.get("last_reading_at")
    return last is None or reading.recorded_at > datetime.fromisoformat(last)


async def _resolve(
    alerts: AlertRepository, alert: Alert, now: datetime, resolution: str | None = None
) -> None:
    """Resolve an unresolved alert, re-reading it if someone (e.g. an acknowledge) won the race.

    ``resolution`` records why in ``details``; without it the alert was auto-resolved by recovery.
    """
    current: Alert | None = alert
    for _ in range(_RESOLVE_ATTEMPTS):
        if current is None or not current.is_unresolved:
            return
        try:
            # An alert is never resolved before it opened (e.g. a delayed or backlog trigger).
            resolved = current.resolve(max(now, current.opened_at))
            if resolution is not None:
                resolved = replace(resolved, details={**resolved.details, "resolution": resolution})
            await alerts.update(resolved)
            return
        except ConcurrentAlertUpdateError:
            current = await alerts.get(current.id)
    logger.warning("could not resolve alert %s after %d attempts", alert.id, _RESOLVE_ATTEMPTS)


class EvaluateReadingAlerts:
    """Reacts to a newly stored reading: out-of-range alerts and silent-sensor recovery.

    Only readings of a tank with an active batch, recorded since that batch started, count. All
    timing uses ``recorded_at``. Sensors of one tank are evaluated together per measurement.
    """

    def __init__(
        self,
        readings: ReadingRepository,
        batches: BatchRepository,
        alerts: AlertRepository,
        rules: AlertRules,
        new_id: Callable[[], UUID] = uuid4,
    ) -> None:
        self._readings = readings
        self._batches = batches
        self._alerts = alerts
        self._rules = rules
        self._new_id = new_id

    async def execute(self, reading: Reading) -> None:
        batch = await self._batches.get_active(reading.tank_id)
        if batch is None or batch.started_at is None or reading.recorded_at < batch.started_at:
            return
        # Any reading proves the sensor is alive, whatever it measures.
        silent = await self._alerts.get_unresolved(reading.tank_id, AlertKind.SILENT_SENSOR, None)
        if silent is not None and _proves_recovery(silent, reading):
            # A backlog reading recorded before the alert opened still proves the sensor was
            # reporting: the alert closes at its own opening instant and says so.
            late = reading.recorded_at < silent.opened_at
            await _resolve(self._alerts, silent, reading.recorded_at, LATE_DATA if late else None)
        if reading.measurement in ALERTABLE_MEASUREMENTS:
            await self._evaluate_range(batch, batch.started_at, reading)

    async def _evaluate_range(self, batch: Batch, started_at: datetime, incoming: Reading) -> None:
        # Evaluate as of the newest stored reading of this series, not the incoming one: a late or
        # out-of-order reading must not decide on stale history (resolve an alert that newer
        # readings keep violating, or open one backdated into a period known to be in range).
        newest = (
            (await self._readings.latest_per_measurement([incoming.tank_id]))
            .get(incoming.tank_id, {})
            .get(incoming.measurement)
        )
        reading = newest if newest and newest.recorded_at >= incoming.recorded_at else incoming
        low, high = target_bounds(batch.targets, reading.measurement)
        bound = out_of_range(reading.value, batch.targets, reading.measurement)
        in_range = bound is None
        # Bounded below only by the batch start, never by a time horizon: with a series sparser
        # than any threshold a horizon would hide the previous reading and the streak could never
        # be seen to last. The adapter's scan is as long as the current streak (see its comment).
        streak_start = await self._readings.streak_start(
            reading.tank_id,
            reading.measurement,
            low,
            high,
            in_range,
            started_at,
            reading.recorded_at,
        )
        if streak_start is None:  # the newest instant mixes sensors in and out of range
            return
        existing = await self._alerts.get_unresolved(
            reading.tank_id, AlertKind.OUT_OF_RANGE, reading.measurement
        )
        action = decide_out_of_range(
            is_open=existing is not None,
            in_range=in_range,
            streak_start=streak_start,
            now=reading.recorded_at,
            rules=self._rules,
        )
        if action is AlertAction.RESOLVE and existing is not None:
            await _resolve(self._alerts, existing, reading.recorded_at)
        elif action is AlertAction.OPEN:
            await self._alerts.add(
                Alert(
                    id=self._new_id(),
                    tank_id=reading.tank_id,
                    batch_id=batch.id,
                    kind=AlertKind.OUT_OF_RANGE,
                    measurement=reading.measurement,
                    status=AlertStatus.OPEN,
                    opened_at=reading.recorded_at,
                    details={
                        "observed": reading.value,
                        "bound": bound,
                        "target_min": low,
                        "target_max": high,
                    },
                )
            )


class CheckSilentSensors:
    """Opens a silent-sensor alert for each active batch whose tank stopped reporting.

    Silence is measured from the tank's newest reading since the batch started, or from the batch
    start when it has sent none. Recovery is handled by ``EvaluateReadingAlerts``.
    """

    def __init__(
        self,
        readings: ReadingRepository,
        batches: BatchRepository,
        alerts: AlertRepository,
        rules: AlertRules,
        clock: Clock,
        new_id: Callable[[], UUID] = uuid4,
    ) -> None:
        self._readings = readings
        self._batches = batches
        self._alerts = alerts
        self._rules = rules
        self._clock = clock
        self._new_id = new_id

    async def execute(self) -> None:
        active = await self._batches.list(status=BatchStatus.ACTIVE)
        if not active:
            return
        latest = await self._readings.latest_per_measurement([b.tank_id for b in active])
        now = self._clock()
        for batch in active:
            if batch.started_at is None:  # pragma: no cover - active batches always have it
                continue
            started_at = batch.started_at
            seen = [
                r.recorded_at
                for r in latest.get(batch.tank_id, {}).values()
                if r.recorded_at >= started_at
            ]
            last_reading = max(seen) if seen else None
            if not is_silent(last_reading or started_at, now, self._rules):
                continue
            await self._alerts.add(
                Alert(
                    id=self._new_id(),
                    tank_id=batch.tank_id,
                    batch_id=batch.id,
                    kind=AlertKind.SILENT_SENSOR,
                    measurement=None,
                    status=AlertStatus.OPEN,
                    opened_at=now,
                    details={"last_reading_at": last_reading.isoformat() if last_reading else None},
                )
            )


async def _unresolved(alerts: AlertRepository, batch_id: UUID | None = None) -> list[Alert]:
    found: list[Alert] = []
    for status in (AlertStatus.OPEN, AlertStatus.ACKNOWLEDGED):
        found += await alerts.list(status=status, batch_id=batch_id)
    return found


class ResolveBatchAlerts:
    """Resolves the unresolved alerts of a just-finished batch (an ``after_finished`` hook).

    Alerts only make sense while their batch is active; the resolution is dated at the finish.
    """

    def __init__(self, alerts: AlertRepository) -> None:
        self._alerts = alerts

    async def execute(self, batch: Batch) -> None:
        when = batch.finished_at
        if when is None:  # pragma: no cover - the hook receives finished batches
            return
        for alert in await _unresolved(self._alerts, batch.id):
            await _resolve(self._alerts, alert, when, BATCH_FINISHED)


class ResolveOrphanAlerts:
    """Safety net: resolves unresolved alerts whose batch is not active.

    Repairs what ``ResolveBatchAlerts`` missed (a crash or failure right after a finish).
    """

    def __init__(self, batches: BatchRepository, alerts: AlertRepository, clock: Clock) -> None:
        self._batches = batches
        self._alerts = alerts
        self._clock = clock

    async def execute(self) -> None:
        unresolved = await _unresolved(self._alerts)
        if not unresolved:
            return
        active = {b.id for b in await self._batches.list(status=BatchStatus.ACTIVE)}
        now = self._clock()
        for alert in unresolved:
            if alert.batch_id not in active:
                await _resolve(self._alerts, alert, now, BATCH_FINISHED)
