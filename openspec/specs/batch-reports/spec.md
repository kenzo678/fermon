# Batch Reports Specification

Resumen: reportes deterministas por lote (PDF y CSV, sin IA) con estadísticas por medición, % de tiempo en
rango, ABV frente al esperado, alertas y análisis de laboratorio; parciales para lotes activos.

## Purpose

A brewery needs to document each fermentation. A batch report gathers the batch data, the statistics of its
readings, its alerts and its lab analyses into a PDF or a CSV that is a pure function of stored data (no AI,
no randomness), so the same batch at the same instant always gives the same report.

## Requirements

### Requirement: Report endpoints and access

The API MUST expose `GET /batches/{id}/report.pdf` (`application/pdf`) and `GET /batches/{id}/report.csv`
(`text/csv; charset=utf-8`). Both MUST answer with `Content-Disposition: attachment` and the filename
`batch-<beer-slug>-<YYYY-MM-DD>.<ext>`, where the slug is lowercase ASCII (`[a-z0-9-]`, `beer` when empty) and
the date is the generation date (UTC). Any authenticated role, including `viewer`, MAY download them; without
a session the response MUST be `401`. An unknown batch MUST be `404` with `field` `batch_id` and a `planned`
batch MUST be `409` with `field` `status`. Active and finished batches MUST produce a report.

#### Scenario: A viewer downloads a finished batch report
- GIVEN a finished batch and a signed-in `viewer`
- WHEN `GET /batches/{id}/report.pdf` is sent
- THEN the response is `200` with `Content-Type` `application/pdf`
- AND `Content-Disposition` is `attachment; filename="batch-pale-ale-2026-01-01.pdf"`
- AND the body starts with `%PDF`

#### Scenario: Planned batch
- GIVEN a `planned` batch
- WHEN either report endpoint is requested
- THEN the response is `409` with `field` `status`

#### Scenario: Unknown batch and no session
- GIVEN an unknown batch id
- WHEN a report endpoint is requested with a session
- THEN the response is `404` with `field` `batch_id`
- AND the same request without a session is `401`

### Requirement: Report window and partial reports

The report MUST cover `[started_at, finished_at]` of a finished batch and `[started_at, now]` of an active one,
using an injectable clock. A report of an active batch MUST be marked `Partial (batch in progress)` (PDF badge
and CSV `report` row); a finished one MUST be marked `Complete`. Readings recorded after `finished_at` MUST NOT
be included.

#### Scenario: Active batch
- GIVEN an active batch started three hours ago
- WHEN its CSV report is requested
- THEN the `report` row is `Partial (batch in progress)`
- AND the window ends at the time of the request

### Requirement: Readings resolution and statistics

Statistics MUST be computed from the 1-minute aggregates of the batch's tank (`readings_1m`), never from raw
readings. For each measurement with data, the report MUST give: `count` (raw readings), `min`, `max`, `mean`
(weighted by reading count), `first` and `last` (averages of the first and last minute) and the batch target
range (`target_min`, `target_max`; either may be null). A measurement without data MUST NOT appear.

#### Scenario: Statistics weighted by readings
- GIVEN a minute with 2 readings averaging 19.0 and another with 6 readings averaging 20.0
- WHEN the report is built
- THEN `count` is 8 and `mean` is 19.75

### Requirement: Time-weighted percentage in range

The percentage of time within the batch target range MUST be computed from consecutive samples, each holding
its value until the next one. A sample MUST be credited with `min(time to the next sample, max_gap)` and the
last one with `min(time to the window end, max_gap)`, where `max_gap` is configurable
(`REPORT_MAX_GAP_SECONDS`, default 600 s). Silent periods longer than `max_gap` MUST NOT count as in range and
MUST be excluded from the observed time. A value is in range when `low <= value <= high`; a missing bound is
open. A measurement with no target (alcohol, or no bound at all) MUST report `null`.

#### Scenario: Gap cap
- GIVEN a sample in range at minute 0 and the next sample (out of range) at minute 60, window end at minute 61
- AND `max_gap` of 10 minutes
- THEN the percentage is 10 / 11 of the observed time, about 90.9 %

#### Scenario: No target
- GIVEN the alcohol measurement
- THEN its in-range percentage is `null`

### Requirement: ABV curve versus expected

The report MUST include the alcohol series downsampled to at most 240 points (equal whole-minute buckets from
the batch start, weighted means) and, when the batch has `expected_final_abv` and an `expected_end` after its
start, an expected curve that rises linearly from 0 at `started_at` to `expected_final_abv` at `expected_end`
and stays flat afterwards. Without them there MUST be no expected curve.

#### Scenario: Linear expectation
- GIVEN `expected_final_abv` 5.0, started at T and expected end at T + 20 h
- THEN the expected value at T + 10 h is 2.5

### Requirement: Alerts and lab analyses

The report MUST list the batch's alerts oldest first with kind, measurement, opened, acknowledged and resolved
times, duration (until the window end while unresolved) and resolution (`recovered`, or the stored
`details.resolution`). It MUST list the batch's lab analyses with stage, sampled time, analyst and each value
with its stored status. Who acknowledged an alert is not recorded by the system and MUST NOT be invented.

#### Scenario: Ongoing alert
- GIVEN an unresolved alert opened 90 minutes after the start of a batch that finished at 10 h
- THEN its duration is 8 h 30 min and it is marked ongoing

### Requirement: PDF rendering

The PDF MUST be rendered from an HTML template by WeasyPrint on A4, with a header, batch summary, statistics
table, charts, alerts table, lab table and a footer with the generation timestamp and page numbers. Charts
(temperature, pressure, ABV versus expected, with the target band shaded) MUST be inline SVG generated
deterministically in Python, without JavaScript or a plotting library. All text coming from the user MUST be
escaped. The statistics note MUST state the 1-minute resolution and the gap rule.

#### Scenario: Deterministic content
- GIVEN the same report and generation time
- WHEN the HTML is rendered twice
- THEN both outputs are identical

### Requirement: CSV rendering

The CSV MUST be a single table with a `Batch summary` section (key/value rows: beer, style, tank, status,
report mark, profile, start, end, expected end, duration in hours, expected final ABV, generation time,
resolution, gap cap) and a `Statistics` section with one row per measurement (`measurement`, `unit`, `count`,
`min`, `max`, `mean`, `first`, `last`, `target_min`, `target_max`, `in_range_percent`; empty cells for null).
Text cells starting with `=`, `+`, `-` or `@` MUST be prefixed with `'` so spreadsheets do not run them.

#### Scenario: Formula in a beer name
- GIVEN a beer named `=HYPERLINK(1)`
- WHEN the CSV is generated
- THEN the `beer_name` cell is `'=HYPERLINK(1)`
