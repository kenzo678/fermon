# Tanks Specification

Resumen: los tanques se registran solos con la primera lectura y se consultan con su última lectura por
medición, lote activo y alertas abiertas.

## Purpose

A tank is the physical vessel that readings, batches and alerts hang from. Tanks are never created by hand:
they appear when the first valid reading for them is ingested. The overview gives a dashboard everything it
needs for a tank card in one request.

## Requirements

### Requirement: Auto-registration

The first valid reading of an unknown `tank_id` MUST create a tank with `id` (trimmed `tank_id`), an
optional `display_name` (initially `null`) and `first_seen_at`. Registration MUST be idempotent and
race-free: concurrent first readings of a tank MUST collapse into one row. Migration `0002` MUST create the
`tanks` table and back-fill it from the tank ids already present in `readings`.

#### Scenario: First reading registers the tank
- GIVEN no tank `tank-1`
- WHEN a valid reading for `tank-1` is ingested
- THEN `GET /tanks/tank-1` returns the tank

#### Scenario: Invalid reading registers nothing
- GIVEN no tank `tank-2`
- WHEN a reading for `tank-2` fails validation
- THEN no tank `tank-2` exists

### Requirement: first_seen_at is the earliest reading

`first_seen_at` MUST be the earliest `recorded_at` observed for the tank, even when readings arrive out of
order (QoS 1 redelivery, backlog after an outage). The registration upsert MUST only rewrite the row when
the new instant is strictly earlier than the stored one, so ordinary readings do not create new row versions.

#### Scenario: Out-of-order arrival
- GIVEN a tank first seen at 12:05
- WHEN a reading recorded at 12:00 arrives later
- THEN `first_seen_at` becomes 12:00

#### Scenario: Later reading does not rewrite
- GIVEN a tank first seen at 12:00
- WHEN a reading recorded at 12:10 arrives
- THEN the stored row is not rewritten

### Requirement: Tank list with overview

`GET /tanks` MUST return all tanks ordered by `id`, each shaped as:
`{"id", "display_name", "first_seen_at", "active_batch", "open_alerts", "latest": {"temperature",
"pressure", "alcohol"}}`. `latest.<measurement>` MUST be the newest reading of that measurement or `null`
if the tank never reported it. `active_batch` MUST be the summary of the tank's active batch
(`id`, `beer_name`, `style`, `targets`, `started_at`, `expected_end`) or `null`. `open_alerts` MUST be the
number of unresolved (`open` + `acknowledged`) alerts of the tank. The listed tanks' latest readings, active
batches and alert counts MUST each be resolved with one query for all tanks (no per-tank queries). All
instants MUST be in UTC.

#### Scenario: Tank without readings
- GIVEN a tank that has no pressure reading
- WHEN `GET /tanks` is called
- THEN `latest.pressure` is `null`

#### Scenario: Tank with an active batch and alerts
- GIVEN a tank with an active batch and one open and one acknowledged alert
- WHEN `GET /tanks` is called
- THEN `active_batch` is populated and `open_alerts` is `2`

#### Scenario: Resolved alerts are not counted
- GIVEN a tank whose only alert is resolved
- WHEN `GET /tanks` is called
- THEN `open_alerts` is `0`

### Requirement: Single tank and 404

`GET /tanks/{tank_id}` MUST return the same shape for one tank. A tank id that was never registered MUST
respond `404` with `{"detail": [{"field": "tank_id", "message": ...}]}`; a blank `tank_id` MUST respond
`422`.

#### Scenario: Unknown tank
- GIVEN no tank `nope`
- WHEN `GET /tanks/nope` is called
- THEN the response is `404` with `field` `tank_id`

### Requirement: CORS

The API MUST allow browser calls only from the origins listed in `CORS_ORIGINS` (comma-separated list or
JSON array; default `http://localhost:5173,http://localhost:3000`; docker-compose also adds
`http://frontend-e2e:5173`). Allowed methods are `GET`, `POST` and `PATCH`, allowed header `Content-Type`,
without credentials. The same allow-list MUST be applied to WebSocket handshakes (see `realtime`).

#### Scenario: Preflight from an allowed origin
- GIVEN `CORS_ORIGINS` includes `http://localhost:5173`
- WHEN a preflight `OPTIONS` for `PATCH` arrives from that origin
- THEN the response allows the request

#### Scenario: Preflight from a foreign origin
- GIVEN an origin not in `CORS_ORIGINS`
- WHEN a preflight arrives
- THEN the response does not allow it

### Requirement: Health endpoint

`GET /health` MUST respond `{"status": "ok"}` without touching the database, so it works while the database
is unavailable.

#### Scenario: Database down
- GIVEN the database is unavailable
- WHEN `GET /health` is called
- THEN the response is `200` `{"status": "ok"}`

## Known limitations / future work

- `display_name` has no write path yet; it is always `null` unless set directly in the database.
- No authentication or user model exists (out of scope so far).
