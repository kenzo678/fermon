# Sensor Simulator Specification

Resumen: simulador de dispositivos sensor (proyecto aparte) que publica lecturas por MQTT con perfiles de
fermentación y fallos inyectables.

## Purpose

`simulator/` emulates what a sensor device (sensor + microcontroller) publishes, so the system can be
developed and demonstrated before real ESP32 or industrial sensors exist. It follows the same message
contract as real devices, so sources are interchangeable.

## Requirements

### Requirement: Message output

Every tick the simulator MUST publish, for each tank that is online, three messages with MQTT QoS 1 on
`{prefix}/tanks/{tank_id}/readings` (default prefix `fermon`): sensors `{tank_id}-temp` (`temperature`,
`celsius`), `{tank_id}-pressure` (`pressure`, `bar`) and `{tank_id}-abv` (`alcohol`, `percent_abv`). The
payload MUST be `{"sensor_id", "measurement", "value", "unit", "recorded_at"}` where `recorded_at` is the
REAL UTC time, timezone-aware, and `value` is already in physical units. The topic prefix MUST match the
backend's `MQTT_TOPIC_PREFIX` for readings to be ingested.

#### Scenario: One tick
- GIVEN tanks `tank-1:ale,tank-2:lager` and no faults
- WHEN a tick runs
- THEN six messages are published (two tanks times three sensors) with the exact contract

#### Scenario: Naive timestamps are refused
- GIVEN a reading with a naive `recorded_at`
- WHEN a message is built
- THEN building fails with an error

### Requirement: Fermentation profiles

The simulator MUST provide deterministic profiles as a function of elapsed fermentation time: alcohol follows
a normalized logistic curve (0 at the lag end up to the target ABV at the end of the active phase),
pressure rises from a resting 0.05 bar with fermentation activity up to the profile's maximum, and
temperature oscillates around the target with an exothermic bump at peak activity plus a small 24-hour
drift. Presets MUST be: `ale` (target 19 degC, 5.0 % ABV, lag 6 h, 96 h active phase, max pressure 0.8 bar,
exotherm 1.5 degC) and `lager` (10 degC, 5.2 % ABV, lag 12 h, 240 h, max 1.0 bar, exotherm 1.0 degC).
Pressure and alcohol MUST NOT be negative before fault injection.

#### Scenario: Alcohol bounds
- GIVEN the `ale` profile
- WHEN elapsed time is zero or before the lag
- THEN alcohol is 0
- AND after the active phase it equals 5.0

#### Scenario: Determinism
- GIVEN the same elapsed time
- WHEN the profile is evaluated twice
- THEN the clean values are identical

### Requirement: Accelerated fermentation time

Fermentation time MUST advance `SIM_ACCELERATION` times faster than real time (default 600: 1 real second
= 10 simulated minutes), computed from the real elapsed seconds since startup. `recorded_at` MUST stay the
real UTC time, never accelerated.

#### Scenario: Acceleration
- GIVEN acceleration 600
- WHEN 6 real seconds elapse
- THEN elapsed fermentation time is 1 hour

### Requirement: Fault injection

The simulator MAY inject faults using an injected random source (reproducible with `SIM_SEED`):
- Gaussian noise per measurement (`SIM_TEMPERATURE_NOISE_STD` 0.1, `SIM_PRESSURE_NOISE_STD` 0.01,
  `SIM_ABV_NOISE_STD` 0.05); noisy pressure and alcohol values MUST be clamped to 0 or above.
- Dropped readings with probability `SIM_DROPOUT_RATE` (default 0.02).
- Out-of-range spikes with probability `SIM_SPIKE_RATE` (default 0.01) using the values 150 (temperature),
  25 (pressure), 50 (alcohol), which the backend rejects; spikes MUST NOT be clamped.
- Disconnections with probability `SIM_DISCONNECT_RATE` per tank per tick (default 0.005): the tank publishes
  nothing for `SIM_DISCONNECT_TICKS` ticks in total (default 5).
Setting the three rates and the noise standard deviations to 0 MUST yield a clean signal.

#### Scenario: Reproducible faults
- GIVEN the same `SIM_SEED`
- WHEN two runs generate the same ticks
- THEN the injected faults are identical

#### Scenario: Disconnect window length
- GIVEN `SIM_DISCONNECT_TICKS=5` and a disconnect triggered at tick N
- WHEN ticks N to N+4 run
- THEN the tank is silent exactly those 5 ticks and may publish again at N+5 (unless a new disconnect triggers)

#### Scenario: Dropped reading
- GIVEN `SIM_DROPOUT_RATE=1`
- WHEN a tick runs
- THEN no reading is published

#### Scenario: Silent tank for demos
- GIVEN a tank with an active batch whose simulator is stopped
- WHEN the silence threshold passes
- THEN the backend opens a `silent_sensor` alert (see `alerts`)

### Requirement: Settings validation

Settings (prefix `SIM_`) MUST be validated on load, failing fast: `SIM_TICK_INTERVAL_SECONDS` > 0 (default
1), `SIM_ACCELERATION` > 0, rates between 0 and 1, noise standard deviations >= 0, `SIM_DISCONNECT_TICKS`
>= 1, `SIM_TOPIC_PREFIX` a single non-empty topic level without `+`, `#`, `/` or surrounding whitespace.
`SIM_TANKS` MUST be a comma-separated list of `id:preset` (default `tank-1:ale,tank-2:lager`) with known
presets and unique, non-empty ids. An empty `SIM_SEED` means no seed. Broker defaults: `SIM_MQTT_HOST`
(`localhost` in code, `mosquitto` in Compose), `SIM_MQTT_PORT` 1883.

#### Scenario: Invalid tick interval
- GIVEN `SIM_TICK_INTERVAL_SECONDS=0`
- WHEN settings load
- THEN loading fails

#### Scenario: Unknown preset
- GIVEN `SIM_TANKS=tank-1:porter`
- WHEN settings load
- THEN loading fails listing the available presets

#### Scenario: Duplicate tank ids
- GIVEN `SIM_TANKS=tank-1:ale,tank-1:lager`
- WHEN settings load
- THEN loading fails

### Requirement: Broker reconnection

When the broker connection is lost the simulator MUST log a WARNING and reconnect with exponential backoff
from 1 s capped at 30 s (reset after connecting), and MUST stop promptly when asked to (SIGTERM / SIGINT).

#### Scenario: Broker restarts
- GIVEN the simulator is publishing
- WHEN the broker becomes unavailable and later returns
- THEN publishing resumes after the backoff without restarting the process

### Requirement: Deployment

The simulator MUST run as the Compose service `simulator` under the profile `simulator`, with the `SIM_*`
variables defaulted in `docker-compose.yml`. It MUST not run in the default `docker compose up`.

#### Scenario: Default stack excludes it
- WHEN `docker compose up -d` runs without the profile
- THEN the simulator service is not started

## Known limitations / future work

- A test mutates the frozen fault config via `object.__setattr__` (`R3-disconnect-test-mutates-frozen-config`).
- Integration tests use topic prefix `fermon-test` so they never write into the development database.
