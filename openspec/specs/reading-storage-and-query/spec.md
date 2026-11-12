# Reading Storage and Query Specification

Resumen: almacenamiento de lecturas en una hypertable, consulta de lecturas crudas por rango y series
agregadas (1 min / 1 h) para graficar.

## Purpose

Readings are stored in a TimescaleDB hypertable and exposed to clients as raw ranges and as pre-aggregated
time series so a dashboard can chart days of data without transferring hundreds of thousands of points.

## Requirements

### Requirement: Readings hypertable

Readings MUST be stored in a `readings` table converted to a TimescaleDB hypertable partitioned by
`recorded_at`, with a unique constraint on (`tank_id`, `sensor_id`, `measurement`, `recorded_at`) and an
index on (`tank_id`, `recorded_at` DESC). The table MUST NOT have a foreign key to `tanks` (hypertable);
the ingest path registers the tank before storing the reading.

#### Scenario: Migrations create the hypertable
- GIVEN an empty database
- WHEN `alembic upgrade head` runs
- THEN `readings` is a hypertable with the unique identity constraint and the descending index

### Requirement: Raw readings by range

`GET /tanks/{tank_id}/readings?start=&end=` MUST return the tank's readings in the half-open range
`[start, end)` ordered by `recorded_at` ascending. `start` and `end` are REQUIRED ISO-8601 instants with a
timezone. The response timestamps MUST be in UTC. The endpoint MUST NOT require the tank to exist: an
unknown tank yields an empty list. A range with a naive datetime or `start >= end` MUST respond `422` in the
unified error shape; a blank `tank_id` MUST respond `422`.

#### Scenario: Half-open bounds
- GIVEN readings at 12:00:00 and 13:00:00
- WHEN the range `[12:00:00, 13:00:00)` is requested
- THEN only the 12:00:00 reading is returned

#### Scenario: Invalid range
- GIVEN `start` is after `end`
- WHEN the range is requested
- THEN the response is `422`

#### Scenario: Offsets are normalized
- GIVEN a reading stored from a request with a non-UTC offset
- WHEN it is read back
- THEN `recorded_at` is expressed in UTC

### Requirement: Continuous aggregates

The database MUST provide two TimescaleDB continuous aggregates: `readings_1m` (1-minute buckets over
`readings`) and `readings_1h` (1-hour buckets, hierarchical over `readings_1m`, never re-reading raw
readings). Both MUST be keyed by (bucket, `tank_id`, `measurement`), aggregating ALL sensors of that
measurement in the tank together, and MUST store `sum_value`, `min_value`, `max_value` and `sample_count`
(not the average). Both MUST use real-time aggregation (`materialized_only = false`) so not yet
materialized recent data is aggregated on the fly. Refresh policies: `readings_1m` every 1 minute over
[now-2h, now-1min]; `readings_1h` every 30 minutes over [now-3d, now-1h]. The migration downgrade MUST
remove the policies before dropping the views.

#### Scenario: Hourly average is exactly weighted
- GIVEN two minutes holding different numbers of readings
- WHEN the hourly average is computed
- THEN it equals `sum / count` over all readings, not the mean of the minute averages

#### Scenario: Recent data is visible
- GIVEN a reading newer than the last refresh
- WHEN the latest bucket is queried
- THEN the bucket includes that reading through real-time aggregation

### Requirement: Aggregated readings endpoint

`GET /tanks/{tank_id}/readings/aggregated` MUST accept `bucket` (REQUIRED, `1m` or `1h`), `start` and `end`
(REQUIRED, timezone-aware) and `measurement` (OPTIONAL, repeatable; all three when omitted). It MUST return
`{"tank_id", "bucket", "series": {<measurement>: [{"bucket_start", "avg", "min", "max", "count"}]}}`. Each
requested measurement MUST appear in `series`, with an empty list when it has no points; repeated
`measurement` values MUST be de-duplicated. The range is half-open over the bucket start: buckets with
`start <= bucket_start < end` are returned (a `start` in the middle of a bucket excludes that partial
bucket). Points MUST be in ascending order with UTC instants; buckets without readings MUST NOT appear.
The tank MUST exist, otherwise `404`.

#### Scenario: All series by default
- GIVEN a tank with temperature readings only
- WHEN the aggregated endpoint is called without `measurement`
- THEN `series` contains `temperature` with points and `pressure` and `alcohol` as empty lists

#### Scenario: Selected series
- GIVEN `measurement=temperature&measurement=pressure`
- WHEN the endpoint is called
- THEN `series` contains exactly those two keys

#### Scenario: Unknown tank
- GIVEN no tank `nope`
- WHEN the aggregated endpoint is called for it
- THEN the response is `404` in the unified error shape

#### Scenario: Unknown bucket
- GIVEN `bucket=5m`
- WHEN the endpoint is called
- THEN the response is `422`

### Requirement: Point-count guard

If `(end - start) / bucket` exceeds 10 000 points the endpoint MUST respond `422` with a message telling the
client to narrow the range or use a larger bucket. Consequently `1m` admits about 6.9 days and `1h` about
416 days per request. Exactly 10 000 points MUST be accepted.

#### Scenario: Range too large
- GIVEN `bucket=1m` and a range of 30 days
- WHEN the endpoint is called
- THEN the response is `422`

### Requirement: Aggregate refresh boundaries are documented behavior

Real-time aggregation only covers data newer than what is already materialized. A late reading that falls
into an already materialized bucket, or older than the refresh window, MUST NOT be expected to appear until
the aggregate is refreshed manually (`CALL refresh_continuous_aggregate(...)`).

#### Scenario: Late reading in a materialized bucket
- GIVEN a materialized 1-minute bucket
- WHEN a reading belonging to that bucket arrives afterwards
- THEN the aggregated endpoint keeps returning the old bucket values until a manual refresh

### Requirement: Latest reading per measurement

The system MUST be able to resolve the newest reading per (tank, measurement) for many tanks with
index probes independent of history size, breaking same-instant ties deterministically (greatest
`sensor_id` first). This powers the tank overview (see `tanks`) and the alert engine.

#### Scenario: Tie on the same instant
- GIVEN two sensors of one measurement with identical `recorded_at`
- WHEN the latest reading is resolved repeatedly
- THEN the reading of the greatest `sensor_id` is returned each time

## Known limitations / future work

- A very long uninterrupted violation streak makes the alert streak scan proportional to its length (see `alerts`).
- A transient failure in the tank upsert during ingestion lacks a dedicated test
  (`R3-ensure-failure-path-unproved`), and an HTTP test with a repeated `measurement` parameter is missing
  (`R3-duplicate-measurement-param-untested`).
- Occasional flakiness seen once: `TRUNCATE` on the hypertable in integration fixtures can clash with the
  continuous-aggregate refresh job (`tuple concurrently deleted`); not reproduced.
