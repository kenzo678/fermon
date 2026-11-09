# Fermon

Monitoreo de tanques de fermentación (temperatura, presión y alcohol) para un proyecto de tesis.
Todo el desarrollo se ejecuta dentro de Docker; no se requiere Python en el equipo anfitrión.

## Estructura

- `backend/`: API FastAPI con arquitectura hexagonal (`src/fermon/fermentation/{domain,application,infrastructure}`).
- `simulator/`: simulador de dispositivos sensor (sensor + microcontrolador) que publica lecturas por MQTT.
- `frontend/`: dashboard web (Vite + React + TypeScript + Tailwind), servido en desarrollo por Vite y en producción por nginx.
- `mosquitto/`: configuración del broker MQTT (solo para desarrollo).
- `docker-compose.yml`: servicios `api`, `ingestor`, `frontend`, `timescaledb`, `mosquitto` y `simulator` (este último bajo el perfil `simulator`).
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
| `SIM_TOPIC_PREFIX` | `fermon` | Prefijo del tópico; debe coincidir con `MQTT_TOPIC_PREFIX` del ingestor. Las pruebas de integración usan `fermon-test` para no escribir en la base de desarrollo |
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
simulador --MQTT (QoS 1)--> mosquitto --> ingestor --> TimescaleDB <-- API (GET /tanks, /tanks/{id}/readings)
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

## Tanques y CORS

Los tanques se registran solos: la primera lectura válida de un tanque lo crea en la tabla `tanks`
(`id`, `display_name` opcional, `first_seen_at`). La migración `0002` crea la tabla y la rellena con
los tanques que ya tenían lecturas. No hay clave foránea desde `readings` (es una hypertable); la
ingesta registra el tanque antes de guardar la lectura.

| Endpoint | Respuesta |
| --- | --- |
| `GET /tanks` | Lista de tanques ordenada por `id`, cada uno con su última lectura por medición |
| `GET /tanks/{tank_id}` | Un tanque con la misma forma; `404` si nunca se registró |
| `GET /tanks/{tank_id}/readings?start=&end=` | Lecturas crudas del rango `[start, end)` |

```sh
curl localhost:8000/tanks
curl localhost:8000/tanks/tank-1
```

```json
{
  "id": "tank-1",
  "display_name": null,
  "first_seen_at": "2026-01-01T10:00:00Z",
  "active_batch": null,
  "latest": {
    "temperature": {"tank_id": "tank-1", "sensor_id": "tank-1-temp", "measurement": "temperature",
                    "value": 19.5, "unit": "celsius", "recorded_at": "2026-01-01T12:05:00Z"},
    "pressure": null,
    "alcohol": null
  }
}
```

`latest.<medición>` es `null` si el tanque aún no reportó esa medición. `active_batch` es el resumen
del lote activo del tanque (ver [Lotes](#lotes)) o `null`. Los errores usan la forma
unificada `{"detail": [{"field", "message"}]}` (`404` para un tanque desconocido, `422` para un
`tank_id` en blanco). Todos los instantes se devuelven en UTC.

### CORS

`CORS_ORIGINS` define los orígenes del navegador autorizados a llamar a la API (solo `GET`, `POST` y
`PATCH`, sin credenciales). Acepta una lista separada por comas o un arreglo JSON; por defecto
`http://localhost:5173,http://localhost:3000`:

```sh
CORS_ORIGINS=https://panel.example.com,http://localhost:5173 docker compose up -d api
```

## Lotes

Un lote es una cerveza en un tanque, con sus rangos objetivo. Ciclo de vida: `planned` → `active`
(`start`) → `finished` (`finish`). Reglas:

- Un solo lote `active` por tanque: lo garantizan el caso de uso y un índice único parcial en la base
  (`uq_batches_one_active_per_tank`, migración `0004`). Iniciar un segundo responde `409`.
- Se edita en `planned` y `active`; uno `finished` ya no (`409`). Cualquier otra transición es `409`.
- El tanque debe existir (`404` si no). Los instantes se guardan con zona horaria y se devuelven en UTC;
  `started_at` y `finished_at` los fija el servidor (son la base de los reportes).

| Endpoint | Respuesta |
| --- | --- |
| `GET /batch-templates` | Plantillas con rangos precargados: `ale` y `lager` (`custom` no tiene) |
| `POST /batches` | `201` con el lote en `planned`; `404` tanque desconocido; `422` datos inválidos |
| `GET /batches?tank_id=&status=` | Lotes, los más nuevos primero; filtros opcionales |
| `GET /batches/{id}` | Un lote; `404` si no existe |
| `PATCH /batches/{id}` | Edita solo los campos enviados; `422` inválido, `409` si ya terminó |
| `POST /batches/{id}/start` | `planned` → `active`; `409` si hay otro activo en el tanque o no está planificado |
| `POST /batches/{id}/finish` | `active` → `finished`; `409` si no está activo |

Plantillas: `ale` = 18–21 °C, presión máx. 1.0 bar, ABV 5.0; `lager` = 8–12 °C, presión máx. 1.2 bar,
ABV 5.2. Los campos de `targets` enviados al crear sobrescriben la plantilla (con `custom` son
obligatorios `temperature_min`, `temperature_max` y `pressure_max`). Los límites deben ser coherentes
(mín. < máx.) y estar dentro de los rangos físicos de cada medición; `expected_final_abv` es 0–20.

```sh
curl -X POST localhost:8000/batches -H 'Content-Type: application/json' -d '{
  "tank_id": "tank-1", "beer_name": "Pale Ale", "style": "APA", "template": "ale",
  "targets": {"temperature_max": 22.0}, "expected_end": "2026-02-01T00:00:00Z"
}'
curl -X POST localhost:8000/batches/<id>/start
curl -X PATCH localhost:8000/batches/<id> -H 'Content-Type: application/json' -d '{"notes": "dry hop"}'
curl -X POST localhost:8000/batches/<id>/finish
```

`GET /tanks` y `GET /tanks/{id}` incluyen `active_batch` (`id`, `beer_name`, `style`, `targets`,
`started_at`, `expected_end`), resuelto con una sola consulta para todos los tanques listados.

## Alertas

El backend evalúa alertas solo para tanques con un lote `active`, y solo con lecturas registradas desde
que el lote empezó (`started_at`). Todo el tiempo se mide sobre `recorded_at`, no sobre la hora de llegada.

| Tipo | Se abre cuando | Se resuelve cuando |
| --- | --- | --- |
| `out_of_range` (temperatura o presión) | el valor está fuera del rango del lote durante 5 min seguidos | vuelve al rango y se mantiene 2 min seguidos |
| `silent_sensor` | el tanque no reporta ninguna lectura por 10 min (contados desde el inicio del lote si nunca reportó) | llega una lectura del tanque más nueva que la última que vio la alerta (`details.last_reading_at`) |

- Los límites del rango cuentan como dentro del rango (solo se viola al superarlos); los umbrales de
  tiempo se cumplen al alcanzarlos (`>=`). La presión usa `pressure_max` y, si existe, `pressure_min`.
- El alcohol no genera alertas. Los sensores de un mismo tanque se evalúan en conjunto por medición.
- La evaluación se ancla a la lectura almacenada más nueva de cada tanque y medición, no a la que
  acaba de llegar: una lectura tardía o de un backlog nunca mueve las alertas hacia atrás (no resuelve
  una alerta que las lecturas más nuevas siguen violando ni abre una con fecha en un periodo que ya
  se sabe dentro del rango).
- Una alerta `silent_sensor` solo se resuelve con una lectura estrictamente posterior a su
  `details.last_reading_at`. Si esa lectura se registró antes de abrirse la alerta (backlog tras una
  caída), se resuelve igual con `details.resolution = "late_data"`; `resolved_at` nunca es anterior a
  `opened_at` (invariante del dominio). La recuperación normal no agrega `resolution`.
- La duración fuera (o dentro) del rango se mide hacia atrás hasta la última lectura de la clase
  opuesta, sin límite de ventana salvo el inicio del lote: funciona igual con sensores que reportan
  con menos frecuencia que los umbrales (por ejemplo, una lectura cada 15 min).
- La histéresis de 2 min evita que un valor que oscila sobre el límite abra y cierre alertas.
- Ciclo de vida: `open` → `acknowledged` (`acknowledge`) → `resolved`; también `open` → `resolved`.
  Una alerta reconocida igual se resuelve sola. Otras transiciones son inválidas.
- Hay a lo sumo una alerta sin resolver por tanque, tipo y medición (índice único parcial
  `uq_alerts_one_unresolved`, migración `0005`); al resolverse, un nuevo episodio abre otra alerta.
- La evaluación por lectura corre en el ingestor y también en `POST /readings`, después de guardar la
  lectura; un fallo de la evaluación se registra y nunca pierde la lectura. El ingestor además revisa
  sensores silenciosos de forma periódica. El estado sale de la base, no de memoria, así que una
  evaluación perdida se recupera con la siguiente lectura o la siguiente revisión.

| Variable | Valor por defecto | Significado |
| --- | --- | --- |
| `ALERT_OUT_OF_RANGE_SECONDS` | `300` | Tiempo fuera de rango para abrir la alerta |
| `ALERT_RESOLVE_SECONDS` | `120` | Tiempo de vuelta al rango para resolverla |
| `ALERT_SILENT_SECONDS` | `600` | Silencio del sensor para abrir `silent_sensor` |
| `ALERT_SILENT_CHECK_INTERVAL_SECONDS` | `60` | Cada cuánto el ingestor revisa sensores silenciosos |

Todas deben ser mayores que 0. Con valores chicos (por ejemplo `20`, `10`, `30`, `5`) se ven alertas en
segundos. Los endpoints de listado y reconocimiento llegan en la siguiente tarea.

## Series agregadas

Para graficar no se piden lecturas crudas (una fermentación de 10 días a 1 lectura/s son cientos de
miles de puntos) sino agregados por cubo de tiempo. La migración `0003` crea dos *continuous
aggregates* de TimescaleDB: `readings_1m` (cubos de 1 minuto, sobre `readings`) y `readings_1h`
(cubos de 1 hora, jerárquico sobre `readings_1m`, así nunca relee las lecturas crudas).

```sh
curl 'localhost:8000/tanks/tank-1/readings/aggregated?bucket=1m&start=2026-01-01T12:00:00Z&end=2026-01-01T13:00:00Z'
curl 'localhost:8000/tanks/tank-1/readings/aggregated?bucket=1h&measurement=temperature&measurement=pressure&start=...&end=...'
```

```json
{
  "tank_id": "tank-1",
  "bucket": "1m",
  "series": {
    "temperature": [
      {"bucket_start": "2026-01-01T12:00:00Z", "avg": 19.0, "min": 18.0, "max": 20.0, "count": 2}
    ],
    "pressure": [],
    "alcohol": []
  }
}
```

- `bucket` (obligatorio): `1m` o `1h`. `start` y `end` (obligatorios, con zona horaria).
  `measurement` es opcional y repetible; sin él se devuelven las tres series. Cada medición pedida
  aparece en `series`, con lista vacía si no tiene puntos.
- El rango es semiabierto sobre el inicio del cubo: se devuelven los cubos con
  `start <= bucket_start < end`. Un `start` que cae a mitad de un cubo excluye ese cubo parcial.
  Los puntos van en orden ascendente y los instantes en UTC.
- Cada punto agrega **todos los sensores** de esa medición en el tanque (`avg`, `min`, `max`,
  `count`). Los cubos sin lecturas no aparecen.
- `readings_1h` guarda la suma y la cantidad, no el promedio: el promedio horario es el ponderado
  exacto (`sum / count`), no el promedio de los promedios por minuto.
- Límite: si `(end - start) / bucket` supera 10 000 puntos responde `422`
  (`1m` admite ~6,9 días por consulta; `1h`, ~416 días). Tanque desconocido: `404`. Los errores usan
  la forma unificada `{"detail": [{"field", "message"}]}`.
- Agregación en tiempo real (`materialized_only = false`): los datos aún no materializados se
  agregan al vuelo, así el último cubo incluye lecturas recientes. Esto solo cubre datos
  **posteriores** a lo ya materializado.
- Políticas de refresco: `readings_1m` cada 1 min sobre la ventana [ahora-2 h, ahora-1 min];
  `readings_1h` cada 30 min sobre [ahora-3 días, ahora-1 h]. Una lectura tardía que cae en un cubo
  ya materializado, o más antigua que la ventana, no se ve hasta refrescar a mano:

```sh
docker compose exec timescaledb psql -U fermon -d fermon -c \
  "CALL refresh_continuous_aggregate('readings_1m', '2026-01-01', '2026-01-02')"
docker compose exec timescaledb psql -U fermon -d fermon -c \
  "CALL refresh_continuous_aggregate('readings_1h', '2026-01-01', '2026-01-02')"
```

## Tiempo real (WebSocket)

`ws://localhost:8000/ws/tanks/{tank_id}` envía cada lectura nueva del tanque como un mensaje de
texto JSON, con la misma forma que `ReadingOut` de la API REST (instantes en UTC):

```json
{"tank_id": "tank-1", "sensor_id": "tank-1-temp", "measurement": "temperature",
 "value": 19.5, "unit": "celsius", "recorded_at": "2026-01-01T12:05:00Z"}
```

Cómo funciona: al guardar una lectura **nueva** (no un duplicado), el adaptador de persistencia
ejecuta `pg_notify('fermon_readings', <json>)` en la misma transacción del `INSERT`. PostgreSQL
entrega la notificación solo al confirmar (`COMMIT`), así que el panel nunca ve datos que no estén
en la base. Tanto `POST /readings` como el ingestor MQTT pasan por ese adaptador. La API mantiene
una conexión dedicada con `LISTEN` y reparte cada mensaje a los clientes suscritos a ese tanque.

- Tanque desconocido o `tank_id` en blanco: el servidor acepta y cierra de inmediato con el código
  `4404` y un motivo. El `tank_id` se normaliza (espacios) igual que en REST.
- Códigos de cierre del WebSocket:

  | Código | Significado |
  | ------ | ----------- |
  | `1011` | Error interno: falló la consulta del tanque (p. ej. base de datos caída). El servidor acepta y cierra con el motivo `internal error` y registra el error. Reintente más tarde. |
  | `4403` | Origen no permitido (ver abajo). |
  | `4404` | Tanque desconocido o `tank_id` en blanco. |

- Origen no permitido: si el encabezado `Origin` no está en `CORS_ORIGINS` se acepta el
  apretón de manos y se cierra de inmediato con `4403` y un motivo, para que el navegador lo
  observe (CORS no cubre WebSockets, por eso se valida aparte). Los clientes sin
  `Origin` (scripts, `websocat`) se aceptan: la restricción protege contra páginas de otros sitios,
  no es autenticación.
- Semántica de entrega: transmisión **en vivo y de mejor esfuerzo**, sin repetición. Las lecturas
  guardadas mientras el cliente estaba desconectado, o mientras la API había perdido su conexión de
  escucha (se reconecta sola con espera de 1 a 30 s), no se reenvían. Al (re)conectar, el cliente
  debe completar el hueco con `GET /tanks/{tank_id}/readings` o con los agregados.
- Cliente lento: cada suscriptor tiene una cola acotada de 100 mensajes; si se llena se descarta el
  mensaje **más antiguo** de ese cliente (nunca bloquea a los demás ni al listener).
- Los mensajes que envía el cliente se ignoran. `/health` funciona aunque la base no esté disponible.
- Límite de PostgreSQL: el payload de `NOTIFY` no puede superar 8000 bytes; una lectura ocupa unos
  pocos cientos. Si superara los 7500 bytes se omite la notificación (con una advertencia en el
  log) y la lectura se guarda igualmente.
- El tiempo real nunca afecta a la ingesta: el `pg_notify` va dentro de un `SAVEPOINT`, de modo que
  un error de `NOTIFY` se registra y se descarta sin revertir el `INSERT`.
- Conexión de escucha: ante cualquier error inesperado se registra con traza y se reintenta con la
  misma espera (1 a 30 s). Además, cada 30 s se ejecuta un `SELECT 1` con tiempo límite de 5 s para
  detectar conexiones medio abiertas; si falla, se reconecta.

```sh
docker compose exec api uv run python -c "
import asyncio, websockets
async def main():
    async with websockets.connect('ws://localhost:8000/ws/tanks/tank-1') as ws:
        async for message in ws:
            print(message)
asyncio.run(main())"
```

## Frontend

Se ejecuta dentro de Docker; no se requiere Node en el equipo anfitrión. La URL de la API se
configura con `VITE_API_URL` (por defecto `http://localhost:8000`).

```sh
docker compose up -d frontend                          # servidor de desarrollo en http://localhost:5173
docker compose run --rm --no-deps frontend npm test   # pruebas (Vitest + Testing Library + MSW)
docker compose run --rm --no-deps frontend npm run lint
docker compose run --rm --no-deps frontend npm run typecheck
docker compose run --rm --no-deps frontend npm run build
docker build --target prod -t fermon-frontend:prod frontend   # imagen de producción (nginx)
```

Al agregar dependencias, ejecutar `npm install` dentro del contenedor, reconstruir la imagen
(`docker compose build frontend`) y recrear el volumen de `node_modules`, porque Docker solo lo
inicializa desde la imagen cuando está vacío: `docker compose up -d -V frontend` (o
`docker volume rm fermon_frontend-node-modules`).

Rutas de la SPA: `/` (vista general de tanques) y `/tanks/:tankId` (detalle: tres gráficos
ECharts con promedio y banda mín–máx de temperatura, presión y alcohol, y un selector de rango).
Los rangos son "Last hour" y "Last 6 hours" (buckets de 1 minuto) y "Last 24 hours" y "Last 7 days"
(buckets de 1 hora); todos quedan muy por debajo del límite de 10 000 puntos del backend. El rango
elegido se guarda en la URL (`?range=1h|6h|24h|7d`, por defecto `24h`; un valor inválido vuelve al
valor por defecto). Un tanque inexistente muestra "Tank not found". Cualquier otra ruta muestra
"Page not found". Para servir las rutas
directamente al recargar, la imagen de producción usa el fallback SPA de nginx.


### Pruebas e2e (Playwright)

Corren contra el stack real con el simulador publicando, en Chromium de escritorio y en un
viewport móvil (Pixel 7). El navegador vive dentro de la red de Compose (imagen oficial
`mcr.microsoft.com/playwright:v1.64.1-noble`, misma versión que `@playwright/test`), así que no se
instala ningún navegador en el equipo anfitrión.

```sh
docker compose run --rm api uv run alembic upgrade head   # primero las migraciones
docker compose --profile simulator --profile e2e up -d timescaledb mosquitto api ingestor simulator frontend-e2e
docker compose run --rm e2e                                # npx playwright test
docker compose --profile simulator --profile e2e down
```

Prerrequisitos: migraciones aplicadas y simulador activo (las pruebas esperan tank-1 y tank-2 con
lecturas). El servicio `e2e` espera a que `api` y `frontend-e2e` respondan (healthchecks) y un
`globalSetup` espera hasta 90 s a que existan lecturas de tank-1 y tank-2; si no, falla con un mensaje
claro. `frontend-e2e` es una copia de `frontend`
con `VITE_API_URL=http://api:8000`, una dirección alcanzable desde ese navegador; el `frontend`
normal sigue usando `localhost`. La API acepta el origen `http://frontend-e2e:5173` por defecto en
`CORS_ORIGINS`; si defines esa variable en `.env`, incluye ese origen. Las trazas de las pruebas
fallidas quedan en `frontend/test-results/`.

### Actualizaciones en vivo

La vista general y el detalle abren un WebSocket nativo por tanque (`/ws/tanks/{id}`, derivado de
`VITE_API_URL`: `http` pasa a `ws`, `https` a `wss`, y una base vacía o relativa usa el origen de la
página). Cada lectura nueva reemplaza la última lectura de su medición en las tarjetas solo si su
`recorded_at` es más reciente (las antiguas o duplicadas se ignoran). Los gráficos se refrescan por
REST como máximo una vez cada 15 s por tanque, no con cada lectura.

El indicador junto al título muestra el estado: **Live** (todos los sockets abiertos),
**Reconnecting…** (alguno conectando o reconectando, con espera de 1 s duplicada hasta 30 s y
reiniciada tras un reintento exitoso) y **Offline** (sin conexión, o cierre definitivo con código
4403/4404, que no se reintenta, en todos los tanques). El stream del backend es de mejor esfuerzo y no reenvía lo perdido,
por lo que en cada reconexión el cliente invalida (y vuelve a pedir por REST) la lista, el detalle y
las series agregadas de ese tanque. Las invalidaciones de la lista se agrupan (250 ms) cuando varios
sockets reabren a la vez, y las series agregadas respetan el mismo límite de 15 s por tanque. Un
tanque con cierre definitivo (4403/4404) no marca "Offline" mientras otros sigan transmitiendo.
