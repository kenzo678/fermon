# Realtime Specification

Resumen: tiempo real con PostgreSQL LISTEN/NOTIFY; la API reparte lecturas por tanque y todas las alertas por
WebSocket, con entrega de mejor esfuerzo y relleno por REST.

## Purpose

The dashboard must update without polling and must never show data that is not in the database. Stored
readings and alert revisions are announced through PostgreSQL `NOTIFY`, a single listener connection in the
API fans them out over WebSockets, and clients backfill gaps through the REST API.

## Requirements

### Requirement: Notifications are tied to stored data

When a reading is newly stored (never for a duplicate) the persistence adapter MUST execute
`pg_notify('fermon_readings', <json>)` in the same transaction as the INSERT, so PostgreSQL delivers it only
on COMMIT. When an alert is inserted or updated (only if the insert/update actually happened) it MUST
execute `pg_notify('fermon_alerts', <json>)` in the same transaction. Both `POST /readings` and the MQTT
ingestor go through these adapters. The reading payload has the shape of `ReadingOut`; the alert payload has
the shape of `AlertOut` (timestamps in UTC).

#### Scenario: Duplicate does not notify
- GIVEN a reading already stored
- WHEN the same identity is ingested again
- THEN no notification is emitted

#### Scenario: Rolled-back write does not notify
- GIVEN a write whose transaction rolls back
- WHEN listeners are connected
- THEN they receive nothing

### Requirement: NOTIFY never breaks a write

The `pg_notify` call MUST run inside a SAVEPOINT, so a NOTIFY error is logged (WARNING) and discarded
without rolling back the INSERT/UPDATE. If the encoded payload exceeds 7500 bytes (PostgreSQL's limit is 8000)
the notification MUST be skipped with a WARNING and the write MUST still succeed.

#### Scenario: NOTIFY fails
- GIVEN `pg_notify` raises an error
- WHEN a reading is ingested
- THEN the reading is stored and a WARNING is logged

#### Scenario: Oversized payload
- GIVEN an encoded payload above 7500 bytes
- WHEN the write happens
- THEN no notification is sent and the write succeeds

### Requirement: Single listener with resilience

The API MUST keep one dedicated asyncpg connection that LISTENs on both channels, started in the background
at application startup so the API (and `/health`) comes up even when the database is down. On connection
loss or any unexpected error it MUST log (with traceback for unexpected errors) and reconnect with
exponential backoff from 1 s capped at 30 s (reset after a successful connection). Every 30 seconds it MUST
probe the connection with `SELECT 1` (5 s timeout) to detect half-open connections and reconnect on failure.
Closing a connection MUST be bounded (5 s timeout with a `terminate()` fallback, also when cancelled), and
`stop()` MUST give the task a 1 s grace before cancelling it. A malformed payload MUST be dropped with a
WARNING.

#### Scenario: Database down at startup
- GIVEN the database is unavailable
- WHEN the API starts
- THEN `/health` responds `ok` and the listener keeps retrying

#### Scenario: Half-open connection
- GIVEN the listener connection silently dies
- WHEN the periodic probe fails
- THEN the broadcaster reconnects

### Requirement: Readings WebSocket

`ws://.../ws/tanks/{tank_id}` MUST send each newly stored reading of that tank as a JSON text message with
the `ReadingOut` shape. `tank_id` MUST be normalized (trimmed) like in REST. Messages sent by the client
MUST be ignored.

#### Scenario: Live reading
- GIVEN a client subscribed to `/ws/tanks/tank-1`
- WHEN a reading for `tank-1` is stored
- THEN the client receives it as a JSON text message
- AND readings of other tanks are not delivered

### Requirement: Alerts WebSocket

`ws://.../ws/alerts` MUST send every stored alert revision of any tank as a JSON text message
`{"type": "alert", "alert": <AlertOut>}`: one message when an alert opens, one when it is acknowledged and
one when it resolves. Messages sent by the client MUST be ignored.

#### Scenario: Full lifecycle
- GIVEN a subscriber on `/ws/alerts`
- WHEN an alert opens, is acknowledged and is resolved
- THEN three messages arrive with `alert.status` `open`, `acknowledged`, `resolved`

### Requirement: Close codes

The server MUST accept the WebSocket handshake first and then close with an application code, so browsers can
observe it:
- `4403` - `Origin` header present and not in `CORS_ORIGINS` (a wildcard `*` allows all); reason
  `origin not allowed`. Clients without an `Origin` header (scripts) MUST be accepted.
- `4404` - unknown or blank `tank_id` (readings socket only).
- `1011` - internal error: the tank lookup failed (readings socket), or the alert feed subscription failed
  (alerts socket); reason `internal error`.

#### Scenario: Unknown tank
- GIVEN no tank `tank-nope`
- WHEN a client connects to `/ws/tanks/tank-nope`
- THEN the server accepts and closes with code `4404`

#### Scenario: Foreign origin
- GIVEN an `Origin` not in `CORS_ORIGINS`
- WHEN a client connects to either socket
- THEN the server accepts and closes with code `4403` and reason `origin not allowed`

#### Scenario: Lookup failure
- GIVEN the database fails during the tank lookup
- WHEN a client connects to `/ws/tanks/tank-1`
- THEN the server closes with `1011` and reason `internal error`

### Requirement: Best-effort delivery and backfill

Delivery MUST be live and best-effort with no replay. Messages for events that happened while the client was
disconnected, or while the API's listener connection was down, are not re-sent. Clients MUST backfill through
`GET /tanks/{tank_id}/readings`, the aggregated endpoint, and `GET /alerts` after (re)connecting.

#### Scenario: Missed events
- GIVEN a client disconnected while readings were stored
- WHEN it reconnects
- THEN it does not receive the missed readings over the socket
- AND they remain available through REST

### Requirement: Slow clients

Each subscriber MUST have a bounded queue of 100 messages. When the queue is full the OLDEST message of that
subscriber MUST be discarded; a slow subscriber MUST NOT block other subscribers or the listener.

#### Scenario: Queue overflow
- GIVEN a subscriber that is not draining its queue
- WHEN more than 100 messages arrive
- THEN it keeps the 100 newest and other subscribers are unaffected

## Known limitations / future work

- Notifications emitted while the listener is disconnected are lost (clients backfill via REST).
- Authentication is not implemented; the Origin check protects against other web pages, it is not
  authentication.
