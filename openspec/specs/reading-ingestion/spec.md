# Reading Ingestion Specification

Resumen: cómo entran las lecturas de sensores al sistema (MQTT y HTTP), su validación, idempotencia y la
semántica de errores del ingestor.

## Purpose

Sensor devices (real or simulated) report readings of temperature, pressure and alcohol per tank. This
capability defines the single message contract, the domain validation shared by every entry point, the
idempotent storage semantics, and how the standalone ingestor process behaves under failure.

## Requirements

### Requirement: Message contract

A reading MUST be published to the MQTT topic `{prefix}/tanks/{tank_id}/readings` with a JSON payload
`{"sensor_id": str, "measurement": "temperature"|"pressure"|"alcohol", "value": number, "unit": str,
"recorded_at": ISO-8601 with timezone}`. The payload MUST NOT contain additional properties. The `tank_id`
is taken from the topic level (it MUST NOT contain `/`, `+` or `#`). The same fields (plus `tank_id` in the
body) MUST be accepted by `POST /readings`.

#### Scenario: Valid MQTT message is ingested
- GIVEN the ingestor is subscribed to `fermon/tanks/+/readings`
- WHEN a message arrives on `fermon/tanks/tank-1/readings` with a valid payload
- THEN a reading for `tank-1` is validated and stored

#### Scenario: Unexpected topic is dropped
- GIVEN the ingestor is running
- WHEN a message arrives on a topic that does not match `{prefix}/tanks/{tank_id}/readings`
- THEN the message is dropped with a WARNING log and the ingestor keeps running

#### Scenario: Malformed payload is dropped
- GIVEN the ingestor is running
- WHEN a message payload is not valid JSON, has an unknown property, a missing field, a non-numeric
  `value` (including a string), a non-finite value, or a `recorded_at` without timezone
- THEN the message is dropped with a WARNING log and the next message is processed

### Requirement: Domain validation

A reading MUST satisfy the domain rules regardless of the entry point:
- `tank_id` and `sensor_id` MUST be non-blank strings and are stored with surrounding whitespace trimmed.
- `measurement` MUST be one of `temperature`, `pressure`, `alcohol`.
- `value` MUST be a finite real number (booleans are rejected) within the inclusive physical limits of its
  measurement: temperature -20..100, pressure 0..10, alcohol 0..20.
- `unit` MUST equal the single canonical unit of the measurement: `celsius`, `bar`, `percent_abv`.
- `recorded_at` MUST be timezone-aware.

#### Scenario: Value outside physical limits is rejected
- GIVEN a reading with `measurement` `temperature`
- WHEN `value` is `150`
- THEN the reading is rejected with a domain error on field `value`
- AND no tank is registered and nothing is stored

#### Scenario: Limit values are accepted
- GIVEN a `pressure` reading
- WHEN `value` is exactly `0` or exactly `10`
- THEN the reading is accepted

#### Scenario: Wrong unit is rejected
- GIVEN a `temperature` reading with `unit` `fahrenheit`
- WHEN it is ingested
- THEN it is rejected with a domain error on field `unit`

#### Scenario: Identifiers are trimmed
- GIVEN a reading with `tank_id` `"  tank-1 "`
- WHEN it is ingested
- THEN it is stored with `tank_id` `tank-1`

### Requirement: HTTP ingestion and unified error shape

`POST /readings` MUST accept a JSON body with `tank_id`, `sensor_id`, `measurement`, `value`, `unit` and
`recorded_at` (no extra properties) and respond with the stored reading (timestamps in UTC). Every 4xx
error returned by the API MUST use the unified shape `{"detail": [{"field": str|null, "message": str}]}`,
including Pydantic validation errors and domain rule violations, which MUST respond `422`. A malformed
JSON body MUST report `field` as `null`.

#### Scenario: New reading responds 201
- GIVEN no reading exists for the tank, sensor, measurement and `recorded_at`
- WHEN a valid `POST /readings` is sent
- THEN the response is `201` with the stored reading

#### Scenario: Domain violation responds 422 with the unified shape
- GIVEN a body with `value` `500` for a temperature reading
- WHEN `POST /readings` is sent
- THEN the response is `422` with `detail[0].field` equal to `value`

#### Scenario: Pydantic violation uses the same shape
- GIVEN a body with an unknown property
- WHEN `POST /readings` is sent
- THEN the response is `422` with a `detail` list of `{field, message}` items

#### Scenario: Malformed JSON has a null field
- GIVEN a request body that is not valid JSON
- WHEN `POST /readings` is sent
- THEN the response is `422` and the error `field` is `null`

### Requirement: Idempotent ingestion

A reading is identified by (`tank_id`, `sensor_id`, `measurement`, `recorded_at`); the storage layer MUST
enforce this identity as unique. Ingesting an existing identity MUST NOT create a second row and MUST keep
the first stored value (first write wins). `POST /readings` for an existing identity MUST respond `200`
with the STORED (first) reading, whatever value the repeated request carried.

#### Scenario: Duplicate over HTTP returns the first value
- GIVEN a stored reading with value `19.5`
- WHEN the same identity is posted again with value `20.0`
- THEN the response is `200` and its `value` is `19.5`
- AND only one row exists

#### Scenario: Duplicate over MQTT collapses
- GIVEN the broker redelivers a QoS 1 message already stored
- WHEN the ingestor handles it
- THEN no new row is created

### Requirement: Tank auto-registration on ingest

For every valid reading the tank MUST be registered (if unknown) before the reading is stored. A rejected
(invalid) reading MUST NOT register a tank. See the `tanks` capability.

#### Scenario: First valid reading creates the tank
- GIVEN no tank `tank-9` exists
- WHEN a valid reading for `tank-9` is ingested
- THEN `tank-9` exists and the reading is stored

### Requirement: Post-ingest hook is best effort

After a reading is newly stored (never for a duplicate) the system MUST invoke the alert evaluation hook
(see `alerts`) for both entry points (ingestor and `POST /readings`). A failure of the hook MUST be logged
at ERROR level and MUST NOT fail the ingest or cause the MQTT message to be retried.

#### Scenario: Hook failure does not lose the reading
- GIVEN alert evaluation raises an exception
- WHEN a valid reading is ingested
- THEN the reading is stored, an ERROR is logged, and the ingest succeeds

### Requirement: MQTT subscription and delivery semantics

The ingestor MUST subscribe with QoS 1 to `{prefix}/tanks/+/readings` using a persistent session
(`clean_session=false`, client id `fermon-ingestor`) by default, so the broker queues messages while it is
down. The topic prefix (`MQTT_TOPIC_PREFIX`, default `fermon`) MUST be a single non-empty topic level
without `+`, `#`, `/` or surrounding whitespace, otherwise configuration MUST fail at startup. `MQTT_TOPIC`
MUST NOT be supported: defining it MUST fail at startup. The session mode (`MQTT_CLEAN_SESSION`) is
configurable. On broker loss the ingestor MUST reconnect with exponential backoff from 1 s capped at 30 s.

#### Scenario: Invalid prefix fails fast
- GIVEN `MQTT_TOPIC_PREFIX` is `a/b`
- WHEN settings are loaded
- THEN loading fails with a validation error

#### Scenario: MQTT_TOPIC is rejected
- GIVEN the environment defines `MQTT_TOPIC`
- WHEN settings are loaded
- THEN loading fails telling the operator to set `MQTT_TOPIC_PREFIX`

#### Scenario: Broker down
- GIVEN the broker becomes unavailable
- WHEN the ingestor loses its connection
- THEN it logs a WARNING and retries with waits of 1, 2, 4, ... up to 30 seconds

### Requirement: Failure classification while storing

When storing a message fails, the ingestor MUST classify the failure. Transient failures (database or
network unavailable: operational/interface errors, invalidated connections, OS-level errors, timeouts,
and SQLAlchemy connection-pool exhaustion) MUST be retried in place on the same message with exponential
backoff (1, 2, 4, ... capped at 30 s) without disconnecting from the broker. Any other failure
(permanent: constraint violations, programming errors) MUST be logged at ERROR with traceback, topic and a
payload preview (truncated), and the message MUST be dropped so the next one is processed at once.
Domain rule violations MUST be dropped with a WARNING (not retried).

#### Scenario: Database outage is retried
- GIVEN the database is unreachable
- WHEN a valid message is received
- THEN the ingestor retries the same message with backoff and stores it once the database recovers
- AND later messages are processed in order afterwards

#### Scenario: Pool exhaustion is transient
- GIVEN storing raises `sqlalchemy.exc.TimeoutError` (pool limit reached)
- WHEN the failure is classified
- THEN it is treated as transient and retried

#### Scenario: Poison message is dropped
- GIVEN storing raises a non-connectivity error
- WHEN the message is processed
- THEN an ERROR with traceback, topic and payload preview is logged and the message is dropped
- AND the next message is processed immediately

### Requirement: Schema gate at ingestor startup

Before subscribing, the ingestor MUST compare the database's Alembic revision with the code's migration
history and MUST NOT consume messages until the schema is ready:
- `READY` (revision is head): log it and start consuming.
- `BEHIND` (no version table, or revision older than head, or database unavailable): log a WARNING and retry
  with backoff 1 -> 30 s.
- `UNKNOWN_REVISION` (database at a revision the code does not know): log an ERROR and exit with a non-zero
  status.
An Alembic configuration error (missing migrations directory, multiple heads) MUST be logged as ERROR and
exit non-zero. The location of `alembic.ini` MUST be configurable via `ALEMBIC_INI_PATH`.

#### Scenario: Ingestor started before migrations
- GIVEN migrations have not been applied
- WHEN the ingestor starts
- THEN it waits with backoff and does not consume messages (the persistent session keeps them queued)
- AND once `alembic upgrade head` runs it logs the schema is ready and subscribes

#### Scenario: Database from a newer version
- GIVEN the database revision is unknown to this code
- WHEN the ingestor starts
- THEN it logs an ERROR and exits with a non-zero status

### Requirement: Periodic alert maintenance in the ingestor

While consuming, the ingestor MUST run an alert maintenance tick every `ALERT_SILENT_CHECK_INTERVAL_SECONDS`
(default 60): first the orphan-alert sweep, then the silent-sensor check; a failing sweep MUST be logged
and MUST NOT skip the silent check. See `alerts`.

#### Scenario: Maintenance runs alongside consumption
- GIVEN the schema is ready
- WHEN the ingestor is consuming
- THEN the maintenance tick runs periodically until the ingestor stops

## Known limitations / future work

- aiomqtt acknowledges each message on receipt; a message is lost only if the process dies (or stops)
  while retrying it, or on a permanent error. Manual acknowledgement after commit is future work.
- Integration tests publish under the prefix `fermon-test` with a clean session and a unique client id so
  a development ingestor never receives them.
- Alembic downgrade is exercised by tests but not against the development stack.
