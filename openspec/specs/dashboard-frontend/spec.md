# Dashboard Frontend Specification

Resumen: SPA responsive (React) con vista general de tanques, detalle con gráficos agregados, actualización
en vivo por WebSocket y cobertura e2e con Playwright. La UI de lotes y alertas aún no existe.

## Purpose

The web dashboard lets operators see every tank's current state and chart its history from a desktop,
laptop, tablet or phone. It consumes the REST and WebSocket APIs of the backend and degrades gracefully when
either is unavailable.

## Requirements

### Requirement: Routes

The SPA MUST serve `/` (tanks overview) and `/tanks/:tankId` (tank detail). Any other path MUST render a
"Page not found" view. The production image MUST serve the routes on direct load and reload through the
nginx SPA fallback (`try_files $uri /index.html`), serving the HTML shell with `Cache-Control: no-cache` and
the hashed assets as immutable, so a redeploy never leaves a stale shell pointing at removed chunks. The API
base URL MUST come from `VITE_API_URL` (default `http://localhost:8000`).

#### Scenario: Unknown path
- GIVEN the app is loaded
- WHEN the user navigates to `/nope/nope`
- THEN "Page not found" is shown

#### Scenario: Deep link reload in production
- GIVEN the production image
- WHEN `/tanks/tank-1` is requested directly
- THEN the SPA shell is served

### Requirement: Tanks overview

The overview MUST fetch `GET /tanks` with TanStack Query and render one card per tank in an accessible list
named "Tanks": the tank name (`display_name` or `id`) as a link to its detail, the latest value of each
measurement (Temperature in degC with 1 decimal, Pressure in bar with 2 decimals, Alcohol in % ABV with 1
decimal, or an em dash when there is none) and an "Updated" absolute time (a `<time>` element with
`datetime`) from the newest valid reading timestamp (malformed timestamps are ignored; a malformed date
formats as an em dash). It MUST show loading, error (with a retry button) and empty states. When cached data
exists, a failed background refetch MUST keep the grid and show a non-blocking "Couldn't refresh" notice
instead of replacing it with an error.

#### Scenario: Cards for every tank
- GIVEN the API returns two tanks with readings
- WHEN the overview renders
- THEN each tank card shows Temperature, Pressure and Alcohol with units

#### Scenario: Empty
- GIVEN the API returns an empty list
- WHEN the overview renders
- THEN an empty state is shown

#### Scenario: Error with retry
- GIVEN the first fetch fails
- WHEN the overview renders
- THEN an error state with a retry action is shown

#### Scenario: Background refetch failure keeps data
- GIVEN cached tanks and a later refetch that fails
- WHEN the overview re-renders
- THEN the grid stays and "Couldn't refresh" is shown

### Requirement: Responsive layout

The tank grid MUST use one column on phones, two from the `sm` breakpoint, three from `lg` and four from
`xl`. The detail charts MUST stack in one column and use two columns at `lg` and one again at `xl`.

#### Scenario: Phone
- GIVEN a phone-sized viewport
- WHEN the overview renders with at least two tanks
- THEN the second card is below the first

#### Scenario: Desktop
- GIVEN a desktop viewport
- WHEN the overview renders
- THEN at least two cards share a row

### Requirement: Tank detail and charts

The detail page MUST show the tank name, a "Back to tanks" link, the tank id, "First seen" time, a "Time
range" radiogroup and three ECharts line charts (Temperature degC, Pressure bar, Alcohol % ABV) built from
`GET /tanks/{id}/readings/aggregated`. Each chart MUST plot the average line plus a min-max band (stacked
across negative values), a tooltip with average, min and max, and zoom controls; with no points it MUST show
"No data in this range". Zoom MUST be preserved across data refetches (only the series are replaced). The
chart MUST resize with its container and dispose its instance on unmount. An unknown tank (REST `404`) MUST
show "Tank not found" with a way back.

#### Scenario: Three charts
- GIVEN a known tank with data
- WHEN the detail page renders
- THEN three charts named "Temperature (°C) over time", "Pressure (bar) over time" and
  "Alcohol (% ABV) over time" are visible

#### Scenario: Unknown tank
- GIVEN the API returns `404` for the tank
- WHEN the detail page renders
- THEN the heading "Tank not found" and a link back to the overview are shown

#### Scenario: Empty series
- GIVEN a measurement with no points in the range
- WHEN the page renders
- THEN that chart shows "No data in this range"

### Requirement: Time ranges in the URL

The selectable ranges MUST be "Last hour" (`1h`, 1m buckets), "Last 6 hours" (`6h`, 1m), "Last 24 hours"
(`24h`, 1h) and "Last 7 days" (`7d`, 1h), all far below the backend's 10 000-point guard (at most 360
points). The selected range MUST be stored in the URL as `?range=` (omitted for the default `24h`); an
invalid value MUST fall back to `24h`. Changing the range MUST replace the history entry. The query window
MUST be computed from the current time at request time.

#### Scenario: Select a range
- GIVEN the detail page at the default range
- WHEN the user selects "Last hour"
- THEN the URL becomes `/tanks/tank-1?range=1h` and "Last hour" is checked

#### Scenario: Invalid range
- GIVEN the URL `?range=banana`
- WHEN the page loads
- THEN the "Last 24 hours" range is used

### Requirement: Lazy detail chunk

The detail route MUST be loaded lazily so ECharts stays out of the main bundle, wrapped in a loading
fallback and an error boundary that, if the chunk fails to load, shows "This page failed to load" with
"Reload" and "Back to tanks", and resets on navigation. Overview code MUST import readings modules directly
(not through the `readings` barrel); an ESLint `no-restricted-imports` rule MUST enforce this.

#### Scenario: Chunk load failure
- GIVEN the detail chunk cannot be loaded
- WHEN the route renders
- THEN the fallback with "Reload" and "Back to tanks" is shown and the app shell stays up

#### Scenario: Barrel import is rejected
- GIVEN a file importing `../readings` (the barrel) from a feature
- WHEN lint runs
- THEN the rule reports an error

### Requirement: API client error contract

The client MUST join the base URL and path without losing a base path prefix; an empty or relative base
(starting with `/`) MUST target the same origin; a base that is not absolute and does not start with `/`
(for example `localhost:8000`) or any invalid URL MUST fail with `ApiError(0, ..., "Invalid API URL
configuration")`. Network failures MUST become `ApiError` with status `0`; non-2xx responses MUST become
`ApiError(status, detail)` with the backend's unified `detail` list when parseable; a 2xx response with an
empty or non-JSON body MUST become `ApiError(status, [], "Invalid JSON response")`. An aborted request,
during any stage including body reading, MUST propagate the abort reason and never an `ApiError`. Query
retries: 4xx `ApiError`s MUST NOT be retried; network errors and 5xx up to 2 retries.

#### Scenario: 404 detail
- GIVEN the API responds 404 with a unified error body
- WHEN the client parses it
- THEN an `ApiError` with status 404 and the `detail` entries is thrown

#### Scenario: HTML 200
- GIVEN a 200 response whose body is HTML
- WHEN the client parses it
- THEN an `ApiError` "Invalid JSON response" is thrown

#### Scenario: Abort
- GIVEN the caller aborts a request while the body is read
- WHEN the promise settles
- THEN it rejects with the abort reason, not an `ApiError`

#### Scenario: No retry on 4xx
- GIVEN a query failing with status 422
- WHEN retry is decided
- THEN it does not retry

### Requirement: Live updates

The overview and the detail MUST open one native WebSocket per tank to `/ws/tanks/{id}`, with the URL
derived from `VITE_API_URL` (`http` -> `ws`, `https` -> `wss`; an empty or relative base uses the page
origin). Each valid message (right tank, known measurement, numeric value, parseable `recorded_at`) MUST
replace the cached latest reading of that measurement in the list and detail caches ONLY when its
`recorded_at` is strictly newer; older or duplicate readings are ignored and no cache entries are created.
Aggregated series MUST be refetched at most once every 15 seconds per tank (not on every reading). Malformed
JSON MUST be discarded with a warning, and an error thrown by the message consumer MUST be reported as
"Realtime message handler failed", not as a malformed message.

#### Scenario: Newer reading updates the card
- GIVEN a card showing a temperature recorded at 12:00
- WHEN a socket message with a temperature recorded at 12:01 arrives
- THEN the card shows the new value without a page reload

#### Scenario: Older reading ignored
- GIVEN a card showing a reading recorded at 12:01
- WHEN a message recorded at 12:00 arrives
- THEN the card is unchanged

#### Scenario: Chart refresh throttle
- GIVEN readings arriving every second
- WHEN readings keep arriving
- THEN the aggregated series of that tank are refetched at most once per 15 seconds

### Requirement: Reconnection, backfill and connection indicator

Each socket MUST reconnect with exponential backoff (1 s doubling up to 30 s, reset after a successful
open). Close codes `4403` (forbidden origin) and `4404` (unknown tank) are terminal and MUST NOT be retried;
every other close, including `1011` and abnormal closures, and a factory that throws, MUST reconnect. On
every REOPEN (not the first open) the client MUST invalidate and refetch the tank list, the tank detail and
the aggregated series of that tank, because the backend stream is best-effort; list invalidations from
several sockets within 250 ms MUST be coalesced (without restarting an in-flight fetch) and aggregated
refreshes MUST respect the same 15 s per-tank limit. A status indicator MUST show "Live" (all non-terminal
sockets open), "Reconnecting…" (any connecting or reconnecting) or "Offline" (no connection, or only
terminal sockets), exposed as `role="status"` with the label `Connection: <text>`. Terminal sockets MUST be
ignored when aggregating, so one deleted tank does not mark the overview "Offline" while others stream.

#### Scenario: Backend restart
- GIVEN an open socket
- WHEN the connection drops and reopens
- THEN the status passes through "Reconnecting…" back to "Live" and list, detail and aggregates are refetched

#### Scenario: Terminal close
- GIVEN a socket closed with `4404`
- WHEN other tank sockets are open
- THEN the indicator stays "Live" and the closed socket is not retried

#### Scenario: Backoff reset
- GIVEN several failed reconnect attempts
- WHEN a connection opens successfully
- THEN the next failure starts again at 1 s

### Requirement: End-to-end coverage

Playwright e2e tests MUST run against the real stack with the simulator publishing, in two projects (desktop
Chromium and a Pixel 7 viewport), from the container `e2e` (image `mcr.microsoft.com/playwright:v1.64.1-noble`,
same version as `@playwright/test`) inside the Compose network, using the twin service `frontend-e2e`
(`VITE_API_URL=http://api:8000`). The `e2e` service MUST wait for the `api` and `frontend-e2e` healthchecks,
and a global setup MUST wait up to 90 s for readings from `tank-1` and `tank-2`, failing with a clear
message otherwise. The suite covers: overview with three measurements and "Live"; live update without
reload; detail header, range selector and three canvas charts; range persisted in the URL; "Tank not found";
and responsive layout (one column on mobile, at least two per row on desktop). Prerequisites: migrations
applied and the simulator running.

#### Scenario: Run the suite
- GIVEN the stack with the simulator is up and migrated
- WHEN `docker compose run --rm e2e` runs
- THEN the suite runs in both projects and failed-test traces are written to `frontend/test-results/`

#### Scenario: Missing prerequisites
- GIVEN no readings for tank-1 or tank-2 after 90 s
- WHEN the suite starts
- THEN it fails immediately with an explanatory message

## Known limitations / future work

- Batch and alert UI do not exist yet: batch form (templates, start/finish), active batch on cards and
  detail, target bands on charts (T3); alert counter, list with filters, "Acknowledge", live notice via
  `/ws/alerts` (T4); e2e with the simulator forcing a deviation (T5). The `Tank` type in the frontend does
  not yet include `active_batch` or `open_alerts`. See `odd/tasks/batches-and-alerts.md`.
- If the set of tanks changes, all sockets are recreated.
- The detail chunk is about 552 kB (186 kB gzip), above Vite's chunk size warning; the main bundle is about
  300 kB (96 kB gzip) as recorded when the feature was merged.
- The canvas rendering is verified only by e2e (jsdom has no canvas).
- No authentication.
