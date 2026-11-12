# Batches Specification

Resumen: un lote es una cerveza en un tanque con sus rangos objetivo; ciclo `planned` -> `active` ->
`finished`, un solo lote activo por tanque y concurrencia optimista.

## Purpose

A batch records which beer is fermenting in a tank and the target ranges the fermentation should respect.
Targets drive the alert engine (see `alerts`) and, later, per-batch reports (`started_at` / `finished_at`
are the basis of those reports).

## Requirements

### Requirement: Batch data and lifecycle

A batch MUST have `id` (UUID), `tank_id`, `beer_name`, `style`, `template` (`ale` | `lager` | `custom`),
`targets`, `status`, `planned_start`, `created_at`, optional `expected_end`, `started_at`, `finished_at`,
`notes`, and an integer `version` (starts at 1). `beer_name`, `style` and `tank_id` MUST be non-blank
(trimmed). All datetimes MUST be timezone-aware and are returned in UTC. `expected_end`, when present, MUST
be after `planned_start`. The status lifecycle MUST be `planned` -> `active` (`start`) -> `finished`
(`finish`); a planned batch has no `started_at`, an active or finished batch has it, and only a finished
batch has `finished_at`. Any other transition MUST be rejected. `started_at` and `finished_at` MUST be set
by the server clock, not by the client.

#### Scenario: Create a planned batch
- GIVEN tank `tank-1` exists
- WHEN `POST /batches` is sent with `tank_id`, `beer_name`, `style` and a template
- THEN the response is `201` with `status` `planned`, `version` `1` and `started_at` `null`
- AND `planned_start` defaults to the server's current time when not sent

#### Scenario: Start a planned batch
- GIVEN a planned batch in a tank with no active batch
- WHEN `POST /batches/{id}/start` is sent
- THEN the batch becomes `active` with `started_at` set by the server and `version` incremented

#### Scenario: Finish an active batch
- GIVEN an active batch
- WHEN `POST /batches/{id}/finish` is sent
- THEN the batch becomes `finished` with `finished_at` set and `version` incremented

#### Scenario: Invalid transitions are conflicts
- GIVEN a batch that is not `planned`
- WHEN `POST /batches/{id}/start` is sent
- THEN the response is `409` with `field` `status`
- AND finishing a batch that is not `active` is also `409`

### Requirement: Target ranges and templates

Targets MUST be `temperature_min`, `temperature_max`, `pressure_max` (all required), `pressure_min`
(optional) and `expected_final_abv` (optional). Values MUST be finite real numbers inside the physical
limits of their measurement (temperature -20..100, pressure 0..10, ABV 0..20), `temperature_min` MUST be
lower than `temperature_max`, and `pressure_min`, when present, MUST be lower than `pressure_max`.
`GET /batch-templates` MUST list the presets: `ale` = 18-21 degC, pressure max 1.0 bar, ABV 5.0;
`lager` = 8-12 degC, pressure max 1.2 bar, ABV 5.2. `custom` has no preset. On create, the fields sent in
`targets` MUST override the template; with `custom` the three required fields MUST be provided. The
default `template` of `POST /batches` is `custom`.

#### Scenario: Template with override
- GIVEN `template` `ale` and `targets.temperature_max` `22.0`
- WHEN the batch is created
- THEN `temperature_min` is `18.0`, `temperature_max` is `22.0`, `pressure_max` is `1.0`

#### Scenario: Custom without required targets
- GIVEN `template` `custom` and no `temperature_min`
- WHEN the batch is created
- THEN the response is `422` with `field` `temperature_min`

#### Scenario: Inconsistent range
- GIVEN `temperature_min` `25` and `temperature_max` `20`
- WHEN the batch is created
- THEN the response is `422` with `field` `temperature_max`

#### Scenario: Template list
- WHEN `GET /batch-templates` is called
- THEN exactly `ale` and `lager` are returned with their targets

### Requirement: Tank must exist

Creating a batch for a tank that was never registered MUST respond `404` (field `tank_id`). Unknown batch
ids MUST respond `404` (field `batch_id`).

#### Scenario: Unknown tank
- GIVEN no tank `ghost`
- WHEN `POST /batches` is sent for `ghost`
- THEN the response is `404`

### Requirement: One active batch per tank

At most one batch per tank MAY be `active`. The use case MUST check it and the database MUST enforce it
(partial unique index `uq_batches_one_active_per_tank`), so concurrent starts cannot both succeed. Starting
a second batch in a tank that already has an active one MUST respond `409` with `field` `tank_id`.

#### Scenario: Second active batch
- GIVEN tank `tank-1` has an active batch
- WHEN another planned batch of `tank-1` is started
- THEN the response is `409` with `field` `tank_id`

### Requirement: Editing

`PATCH /batches/{id}` MUST edit only the fields sent among `beer_name`, `style`, `template`, `targets`,
`planned_start`, `expected_end`, `notes`; `targets` MUST be merged field by field over the current ranges
and revalidated. Editing is allowed in `planned` and `active`; a `finished` batch MUST respond `409`
(`field` `status`), including an empty patch. A patch that leaves the batch unchanged MUST NOT write or
increment `version`.

#### Scenario: Partial edit
- GIVEN an active batch
- WHEN `PATCH` sends `{"notes": "dry hop"}`
- THEN only `notes` changes and `version` increases by one

#### Scenario: Empty patch is a no-op
- GIVEN an active batch at version 3
- WHEN `PATCH` sends `{}`
- THEN the response returns the batch with version 3

#### Scenario: Finished batches are not editable
- GIVEN a finished batch
- WHEN a `PATCH` is sent
- THEN the response is `409`

### Requirement: Optimistic concurrency

`PATCH /batches/{id}` MAY include `version` (integer >= 1) as an if-match token: if it differs from the
batch's current version the response MUST be `409` with `field` `version`. The repository MUST update with a
condition on the previous version, so a write racing another one also responds `409` (`version`) instead
of overwriting it.

#### Scenario: Stale version
- GIVEN a batch at version 4
- WHEN `PATCH` sends `version` `3`
- THEN the response is `409` with `field` `version`

### Requirement: Listing and retrieval

`GET /batches` MUST list batches newest first (by creation), optionally filtered by `tank_id` and/or
`status` (`planned`, `active`, `finished`); an invalid `status` MUST respond `422`. `GET /batches/{id}` MUST
return one batch; an id that is not a UUID MUST respond `422`.

#### Scenario: Filter by status
- GIVEN batches in several statuses
- WHEN `GET /batches?status=active` is called
- THEN only active batches are returned

### Requirement: Finishing resolves the batch's alerts

When a batch is finished, its unresolved alerts MUST be resolved with `details.resolution` =
`batch_finished` dated at `finished_at`. A failure of this hook MUST be logged and MUST NOT fail the finish
(the periodic orphan sweep repairs it). See `alerts`.

#### Scenario: Finish with an open alert
- GIVEN an active batch with an open alert
- WHEN the batch is finished
- THEN the alert becomes `resolved` with `details.resolution` `batch_finished`

### Requirement: Active batch on the tank overview

The active batch MUST be exposed in `GET /tanks` and `GET /tanks/{id}` as `active_batch` (see `tanks`).

#### Scenario: Batch becomes visible on start
- GIVEN a planned batch
- WHEN it is started
- THEN `GET /tanks/{tank_id}` returns it as `active_batch`

## Known limitations / future work

- There is no delete operation and no UI yet: the batch and alert UI (forms, alert list, e2e) are the next
  frontend tasks (`odd/tasks/batches-and-alerts.md`, T3-T5).
- The deterministic per-batch report generator (PDF + CSV, no AI) will consume `started_at`, `finished_at`,
  `targets` and the batch's alerts.
