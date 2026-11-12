# Alerts Specification

Resumen: motor de alertas del backend (fuera de rango sostenido y sensor silencioso), ciclo de vida,
anclaje a la lectura más nueva, API REST y umbrales configurables.

## Purpose

The backend watches tanks that have an `active` batch and raises alerts when temperature or pressure stays
outside the batch's target ranges, or when the tank stops reporting. State is derived from stored readings
and the single unresolved alert per key, never from process memory, so a missed evaluation heals on the next
reading or the next periodic check and any number of ingestors or API workers can run.

## Requirements

### Requirement: Scope of evaluation

Alerts MUST be evaluated only for tanks with an `active` batch, and only from readings whose `recorded_at`
is at or after the batch's `started_at`; earlier readings MUST be ignored. All timing MUST be measured on
`recorded_at`, never on arrival time. Alcohol MUST NEVER generate alerts (its target only shows progress).
The sensors of one tank MUST be evaluated together per measurement.

#### Scenario: No active batch
- GIVEN a tank without an active batch
- WHEN readings far outside any range arrive
- THEN no alert is created

#### Scenario: Reading before the batch started
- GIVEN an active batch started at 12:00
- WHEN a reading recorded at 11:59 arrives
- THEN it is ignored by the alert engine

#### Scenario: Alcohol never alerts
- GIVEN an active batch
- WHEN alcohol readings arrive with any value
- THEN no alert is opened for alcohol

### Requirement: Out-of-range alert with hysteresis

For temperature and pressure, an `out_of_range` alert MUST open when the tank's value has been outside the
batch's range for an uninterrupted `out_of_range_after` (default 5 minutes), and MUST resolve when the value
has been back inside the range for an uninterrupted `resolve_after` (default 2 minutes). A value equal to a
limit MUST count as inside (only strictly beyond a limit violates it). Duration thresholds are met when
reached (`>=`). Pressure uses `pressure_max` and, when present, `pressure_min`; temperature uses
`temperature_min` and `temperature_max`. The alert's `details` MUST hold `observed`, `bound` (`below` |
`above`), `target_min` and `target_max` (`null` when unbounded). A value flapping around a limit MUST NOT by
itself open and close alerts.

#### Scenario: Sustained violation opens the alert
- GIVEN an active batch with temperature range 18-21
- WHEN readings stay above 21 for 5 minutes (recorded time)
- THEN one `out_of_range` alert for `temperature` opens with `bound` `above`

#### Scenario: Short violation does not open
- GIVEN readings above range for 4 minutes 59 seconds
- WHEN the engine evaluates
- THEN no alert is opened

#### Scenario: Value equal to the limit is inside
- GIVEN a limit of 21
- WHEN the value is exactly 21
- THEN it counts as in range

#### Scenario: Recovery resolves after the hysteresis window
- GIVEN an open out-of-range alert
- WHEN readings stay inside the range for 2 minutes
- THEN the alert is resolved (without a `resolution` detail)
- AND a recovery shorter than 2 minutes leaves it unresolved

#### Scenario: Acknowledged alert still resolves itself
- GIVEN an acknowledged out-of-range alert
- WHEN the value stays inside the range for the resolve window
- THEN it resolves

### Requirement: Streak measured back to the opposite class

The duration inside or outside the range MUST be measured backwards to the latest reading of the opposite
class, bounded only by the batch's `started_at` (no time horizon), so sensors that report less often than the
thresholds (for example one reading every 15 minutes) still open and resolve alerts correctly. If the newest
instant mixes sensors in and out of range, the engine MUST NOT decide (no streak).

#### Scenario: Sparse series
- GIVEN a sensor reporting every 15 minutes, outside the range since the batch started
- WHEN the second out-of-range reading arrives 15 minutes after the first
- THEN the alert opens

### Requirement: Evaluation is anchored to the newest stored reading

The out-of-range evaluation MUST be anchored to the newest stored reading of the tank and measurement, not
to the one that just arrived. A late or out-of-order reading (broker backlog) MUST NOT resolve an alert that
newer readings keep violating, and MUST NOT open an alert backdated into a period already known to be in
range.

#### Scenario: Late in-range reading
- GIVEN an open alert and newer readings still out of range
- WHEN an older in-range reading arrives
- THEN the alert stays open

### Requirement: Silent sensor alert

A `silent_sensor` alert (no `measurement`) MUST open when the tank with an active batch has reported no
reading for `silent_after` (default 10 minutes), counted from the tank's newest reading since the batch
started, or from the batch's `started_at` if it never reported. `details.last_reading_at` MUST hold the ISO
instant of that newest reading, or `null`. The alert opens at the check time (the server clock) and MUST be
created by the periodic check, not by readings. At most one unresolved silent alert per tank may exist.

#### Scenario: Tank stops reporting
- GIVEN an active batch whose tank last reported 11 minutes ago
- WHEN the silent-sensor check runs
- THEN a `silent_sensor` alert opens with `details.last_reading_at` equal to that reading

#### Scenario: Never reported
- GIVEN an active batch started 11 minutes ago with no readings
- WHEN the check runs
- THEN a `silent_sensor` alert opens with `last_reading_at` `null`

### Requirement: Silent alert recovery

A `silent_sensor` alert MUST resolve when a reading of the tank (any measurement, recorded in the batch) is
STRICTLY newer than `details.last_reading_at` (any reading qualifies when it is `null`). If that reading was
recorded before the alert opened (backlog after an outage), the alert MUST still resolve, with
`details.resolution` = `late_data`, and `resolved_at` MUST NOT be earlier than `opened_at`. Normal recovery
MUST NOT add a `resolution`. A reading equal to or older than `last_reading_at` MUST NOT resolve the alert.

#### Scenario: Normal recovery
- GIVEN an open silent alert
- WHEN a reading newer than the alert's opening arrives
- THEN the alert resolves without a `resolution` detail

#### Scenario: Backlog reading
- GIVEN an open silent alert opened at 12:20 with `last_reading_at` 12:00
- WHEN a reading recorded at 12:10 arrives
- THEN the alert resolves with `details.resolution` `late_data` and `resolved_at` of 12:20

#### Scenario: Old reading proves nothing
- GIVEN an open silent alert with `last_reading_at` 12:00
- WHEN a reading recorded at 12:00 or earlier arrives
- THEN the alert stays open

### Requirement: Alert lifecycle and invariants

An alert MUST have `id`, `tank_id`, `batch_id`, `kind` (`out_of_range` | `silent_sensor`), `measurement`
(`temperature` | `pressure` for `out_of_range`, `null` for `silent_sensor`), `status`, `opened_at`,
`acknowledged_at`, `resolved_at`, `details` and `version`. The lifecycle MUST be `open` -> `acknowledged` ->
`resolved`, or `open` -> `resolved`; other transitions are invalid. `acknowledged_at` and `resolved_at` MUST
NOT be earlier than `opened_at`. `version` increments on every transition. At most one unresolved alert MUST
exist per (tank, kind, measurement), enforced by the partial unique index `uq_alerts_one_unresolved`
(migration `0005`); after it resolves, a new episode opens a new alert. A racing duplicate open MUST be
treated as an idempotent no-op.

#### Scenario: New episode after resolution
- GIVEN a resolved out-of-range alert
- WHEN the value is again out of range for the threshold
- THEN a new alert is created with a new id

#### Scenario: Duplicate open is a no-op
- GIVEN two evaluations racing to open the same alert
- WHEN both try to insert
- THEN one alert exists and neither fails

### Requirement: Batch finish resolves alerts; orphan sweep

When a batch is finished its unresolved alerts MUST be resolved with `details.resolution` = `batch_finished`.
The periodic maintenance MUST also resolve any unresolved alert whose batch is not active (safety net), with
the same resolution, dated at the sweep time.

#### Scenario: Orphan repaired
- GIVEN an unresolved alert of a finished batch (the finish hook failed)
- WHEN the maintenance tick runs
- THEN the alert is resolved with `batch_finished`

### Requirement: Evaluation entry points

Alert evaluation MUST run after each newly stored reading, for both the ingestor and `POST /readings`; a
failure MUST be logged and MUST NOT lose the reading. The ingestor MUST run the maintenance tick (orphan
sweep, then silent-sensor check) every `ALERT_SILENT_CHECK_INTERVAL_SECONDS` (default 60).

#### Scenario: Evaluation after HTTP ingest
- GIVEN an active batch with violating readings
- WHEN the sustaining reading is posted to `POST /readings`
- THEN the alert opens exactly as with MQTT

### Requirement: Configurable thresholds

The thresholds MUST be configurable by environment variables, all integers greater than 0, otherwise
loading settings fails: `ALERT_OUT_OF_RANGE_SECONDS` (default 300), `ALERT_RESOLVE_SECONDS` (default 120),
`ALERT_SILENT_SECONDS` (default 600), `ALERT_SILENT_CHECK_INTERVAL_SECONDS` (default 60).

#### Scenario: Short thresholds for demos
- GIVEN `ALERT_OUT_OF_RANGE_SECONDS=20`
- WHEN readings stay out of range for 20 seconds
- THEN the alert opens

#### Scenario: Invalid threshold
- GIVEN `ALERT_RESOLVE_SECONDS=0`
- WHEN settings are loaded
- THEN loading fails

### Requirement: Alerts API

`GET /alerts` MUST list alerts newest first (by `opened_at`). Optional filters: `tank_id`, `batch_id`,
`kind` (`out_of_range` | `silent_sensor`), `status` (repeatable) and `limit` (1-500, default 100). Without
`status` only unresolved alerts (`open`, `acknowledged`) MUST be returned; resolved ones are returned only
when requested. `GET /alerts/{id}` MUST return one alert or `404` (field `alert_id`). Invalid filters, a
`limit` out of range, or a non-UUID id MUST respond `422`. Timestamps MUST be in UTC.

#### Scenario: Default list hides resolved
- GIVEN open, acknowledged and resolved alerts
- WHEN `GET /alerts` is called
- THEN only the open and acknowledged ones are returned

#### Scenario: Request resolved explicitly
- GIVEN resolved alerts
- WHEN `GET /alerts?status=resolved` is called
- THEN they are returned

#### Scenario: Limit bound
- WHEN `GET /alerts?limit=501` is called
- THEN the response is `422`

### Requirement: Acknowledge

`POST /alerts/{id}/acknowledge` MUST move an `open` alert to `acknowledged`, stamping `acknowledged_at` with
the server clock. The body is optional and MAY carry `{"version": n}` (>= 1, no other properties). The
operation MUST be idempotent: acknowledging an already acknowledged alert MUST respond `200` with the alert
as is, without writing or changing `version` (whatever `version` the caller sent). A resolved alert MUST
respond `409` (`field` `status`). If a `version` is sent and no longer current, or a write race occurs with a
`version` sent, the response MUST be `409` (`field` `version`). Without `version`, a racing write MUST be
re-read (up to 3 attempts): concurrent acknowledges all succeed, and a concurrent resolution surfaces as the
real `status` conflict.

#### Scenario: First acknowledge
- GIVEN an open alert
- WHEN `POST /alerts/{id}/acknowledge` is sent
- THEN the response is `200`, `status` `acknowledged`, `acknowledged_at` set and `version` incremented

#### Scenario: Repeat acknowledge
- GIVEN an acknowledged alert
- WHEN acknowledge is sent again
- THEN the response is `200` with the same alert and the same `version`

#### Scenario: Resolved alert
- GIVEN a resolved alert
- WHEN acknowledge is sent
- THEN the response is `409` with `field` `status`

#### Scenario: Stale version
- GIVEN an open alert at version 2
- WHEN acknowledge is sent with `{"version": 1}`
- THEN the response is `409` with `field` `version`

#### Scenario: Unknown alert
- WHEN acknowledge is sent for a non-existent id
- THEN the response is `404` with `field` `alert_id`

### Requirement: Live alert notification

Every stored alert revision (opened, acknowledged, resolved) MUST emit a realtime notification, delivered on
`/ws/alerts`. See `realtime`.

#### Scenario: Revision is announced
- GIVEN a subscriber on `/ws/alerts`
- WHEN an alert opens and is later acknowledged
- THEN two messages arrive, with `alert.status` `open` then `acknowledged`

## Known limitations / future work

- The streak scan is proportional to the current streak length (bounded by the batch start); a very long
  uninterrupted streak is the worst case.
- Notifications are best-effort; clients backfill with `GET /alerts` (see `realtime`).
- The alert UI (counter, filters, "Acknowledge" button, live notice) is not built yet (T4 of
  `batches-and-alerts`).
