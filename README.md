# Fermon

Monitoreo de tanques de fermentación (temperatura, presión y alcohol) para un proyecto de tesis.
Todo el desarrollo se ejecuta dentro de Docker; no se requiere Python en el equipo anfitrión.

## Estructura

- `backend/`: API FastAPI con arquitectura hexagonal (`src/fermon/fermentation/{domain,application,infrastructure}`).
- `simulator/`: simulador de dispositivos sensor (sensor + microcontrolador) que publica lecturas por MQTT.
- `mosquitto/`: configuración del broker MQTT (solo para desarrollo).
- `docker-compose.yml`: servicios `api`, `timescaledb`, `mosquitto` y `simulator` (este último bajo el perfil `simulator`).
- `.env.example`: variables de entorno; copiar a `.env` para personalizarlas.

## Comandos de desarrollo

```sh
docker compose up -d                                  # levantar el stack
curl localhost:8000/health                            # {"status": "ok"}
docker compose run --rm api uv run pytest             # todas las pruebas (levanta timescaledb)
docker compose run --rm --no-deps api uv run pytest -m "not integration"  # solo unitarias, sin base de datos
docker compose run --rm api uv run alembic upgrade head  # aplicar migraciones
docker compose run --rm api uv run ruff check .       # lint
docker compose run --rm api uv run ruff format .      # formato
docker compose run --rm api uv run mypy src           # tipos
docker compose down                                   # detener
```

Las pruebas de integración usan la base `fermon_test` (se crea sola); se puede cambiar con
`TEST_DATABASE_URL`.

## Simulador de sensores

`simulator/` es un proyecto Python aparte que emula lo que publica un dispositivo (sensor +
microcontrolador): lecturas ya en unidades físicas, por MQTT con QoS 1, en el tópico
`fermon/tanks/{tank_id}/readings`. Cada tick publica tres lecturas por tanque (`{tank_id}-temp`,
`{tank_id}-pressure`, `{tank_id}-abv`) con el payload
`{"sensor_id", "measurement", "value", "unit", "recorded_at"}`.

El modelo de fermentación (perfiles `ale` y `lager`) es determinista: el alcohol sigue una curva
logística, la presión sube con la actividad fermentativa y la temperatura oscila alrededor del
objetivo. El tiempo de fermentación se acelera (por defecto 1 s real = 10 min simulados, así una
fermentación completa se ve en minutos), pero `recorded_at` siempre es la hora real UTC.
Opcionalmente se inyectan fallos: ruido, lecturas perdidas, picos fuera de rango y desconexiones.

```sh
docker compose --profile simulator up -d              # stack completo + simulador
docker compose --profile simulator up -d mosquitto simulator   # solo broker + simulador
docker compose exec mosquitto mosquitto_sub -t 'fermon/#' -v   # ver los mensajes
docker compose --profile simulator run --rm simulator uv run pytest   # pruebas (incluye integración)
docker compose --profile simulator down
```

Variables de entorno (prefijo `SIM_`, con valores por defecto en `docker-compose.yml`):

| Variable | Defecto | Descripción |
| --- | --- | --- |
| `SIM_MQTT_HOST` / `SIM_MQTT_PORT` | `mosquitto` / `1883` | Broker MQTT |
| `SIM_TANKS` | `tank-1:ale,tank-2:lager` | Tanques `id:perfil` separados por coma |
| `SIM_TICK_INTERVAL_SECONDS` | `1` | Segundos reales entre ticks |
| `SIM_ACCELERATION` | `600` | Factor de aceleración del tiempo de fermentación |
| `SIM_SEED` | vacío | Semilla para reproducir los fallos |
| `SIM_DROPOUT_RATE` | `0.02` | Probabilidad de omitir una lectura |
| `SIM_SPIKE_RATE` | `0.01` | Probabilidad de un valor fuera de rango físico |
| `SIM_DISCONNECT_RATE` | `0.005` | Probabilidad de que un tanque quede mudo `SIM_DISCONNECT_TICKS` ticks (5) |

Para una señal limpia, poner las tres tasas en `0` (y el ruido `SIM_*_NOISE_STD` en `0`).
