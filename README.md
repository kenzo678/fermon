# Fermon

Monitoreo de tanques de fermentación (temperatura, presión y alcohol) para un proyecto de tesis.
Todo el desarrollo se ejecuta dentro de Docker; no se requiere Python en el equipo anfitrión.

## Estructura

- `backend/`: API FastAPI con arquitectura hexagonal (`src/fermon/fermentation/{domain,application,infrastructure}`).
- `simulator/`: simulador de dispositivos sensor (sensor + microcontrolador) que publica lecturas por MQTT.
- `mosquitto/`: configuración del broker MQTT (solo para desarrollo).
- `docker-compose.yml`: servicios `api`, `ingestor`, `timescaledb`, `mosquitto` y `simulator` (este último bajo el perfil `simulator`).
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

## Flujo de punta a punta

```
simulador --MQTT (QoS 1)--> mosquitto --> ingestor --> TimescaleDB <-- API (GET /tanks/{id}/readings)
```

El `ingestor` es un proceso aparte del API (`python -m fermon.ingestor`, servicio `ingestor` de
Compose, que arranca con `docker compose up`). Se suscribe a `fermon/tanks/+/readings` con QoS 1 y
sesión persistente (`clean_session=False`, id `fermon-ingestor`), de modo que el broker encola los
mensajes mientras el ingestor está caído. Cada mensaje se valida (tópico, JSON, esquema y reglas
de dominio) y se guarda con `IngestReading`; los mensajes inválidos se descartan con una
advertencia en el log y nunca detienen el proceso. Si el broker se cae, reconecta con espera
creciente de 1 a 30 s.

Al arrancar, antes de suscribirse, el ingestor compara la revisión de Alembic de la base con el
historial de migraciones del código y distingue tres estados:

- Listo (`READY`): la revisión es `head`; lo informa y empieza a consumir.
- Atrasado (`BEHIND`): no existe la tabla de versión o la revisión es anterior a `head`. Registra
  una advertencia ("run `alembic upgrade head`") y reintenta con espera creciente de 1 a 30 s. Lo
  mismo ocurre si la base no está disponible (advertencia "database unavailable").
- Revisión desconocida (`UNKNOWN_REVISION`): la base está en una revisión que este código no conoce
  (base más nueva o divergente). Esperar no lo arregla, así que el ingestor registra un ERROR
  indicando que hay que desplegar la versión de código que corresponde y sale con estado distinto
  de cero.

Un error de configuración de Alembic (directorio de migraciones inexistente, varios `head`)
tampoco es transitorio: se registra como ERROR y el proceso termina con estado distinto de cero.
Mientras espera no consume, así la sesión persistente de MQTT conserva los mensajes y no se
descarta ninguno por tabla inexistente.

Por defecto el ingestor busca `alembic.ini` en el árbol de fuentes (`backend/alembic.ini`, y las
migraciones junto a él). Si se despliega fuera de ese árbol, indique la ruta con la variable de
entorno `ALEMBIC_INI_PATH`; un `script_location` relativo se resuelve respecto al directorio de ese
archivo.

Semántica de entrega: QoS 1 es "al menos una vez" y la ingesta es idempotente, así que los
duplicados no generan filas repetidas. aiomqtt confirma (ack) cada mensaje al recibirlo, por lo que
el broker no lo reenvía; por eso el ingestor clasifica los fallos al guardar:

- Errores transitorios (base de datos o red no disponibles, p. ej. conexión caída, timeout
  o pool de conexiones agotado): el ingestor no se desconecta y reintenta el mismo mensaje con
  espera creciente (1, 2, 4, ... hasta 30 s), mientras aiomqtt acumula los mensajes siguientes; al
  recuperarse, los procesa en orden.
- Errores permanentes por mensaje (violación de restricciones, errores de programación, etc.): se
  registran en el log con nivel ERROR (traza, tópico y un extracto del payload) y el mensaje se
  descarta; el siguiente se procesa de inmediato, así un mensaje defectuoso no detiene la ingesta.

Un mensaje solo se pierde si el proceso muere (o se detiene) mientras lo está reintentando, o ante
un error permanente. Trabajo futuro: confirmación manual tras el commit.

El prefijo del tópico (`MQTT_TOPIC_PREFIX`, por defecto `fermon`) y la sesión persistente
(`MQTT_CLEAN_SESSION`, por defecto `false`) son configurables. El prefijo debe ser un único nivel de
tópico: no vacío, sin `+`, `#` ni `/` y sin espacios en los extremos; el tópico completo se deriva
de él, por lo que definir `MQTT_TOPIC` no está soportado y provoca un error al arrancar. Los tests
de integración usan el prefijo `fermon-test`, sesión limpia y un id de cliente único por ejecución,
así que un ingestor de desarrollo en ejecución nunca recibe sus mensajes.

```sh
docker compose up -d                                       # api + ingestor + base + broker
docker compose run --rm api uv run alembic upgrade head    # migraciones (la primera vez)
docker compose --profile simulator up -d simulator         # empezar a publicar lecturas
docker compose logs -f ingestor                            # ver el consumo
curl "localhost:8000/tanks/tank-1/readings?start=2026-01-01T00:00:00Z&end=2027-01-01T00:00:00Z"
```

`start` y `end` son instantes ISO-8601 con zona horaria; el rango es `[start, end)`. Aplicar las
migraciones antes de publicar: sin la tabla, cada mensaje falla con un error permanente y se
descarta con un ERROR en el log (ver la semántica de entrega anterior).
