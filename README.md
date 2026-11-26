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
curl -b cookies.txt "localhost:8000/tanks/tank-1/readings?start=2026-01-01T00:00:00Z&end=2027-01-01T00:00:00Z"   # requiere sesión: ver "Autorización"
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
| `PATCH /tanks/{tank_id}` | Pone o borra el nombre visible (`display_name`); solo `admin`; devuelve la forma de `GET /tanks/{tank_id}` |
| `GET /tanks/{tank_id}/readings?start=&end=` | Lecturas crudas del rango `[start, end)` |

```sh
curl -b cookies.txt localhost:8000/tanks
curl -b cookies.txt localhost:8000/tanks/tank-1
# Renombrar (solo admin; los cambios exigen la cookie y X-Requested-With: fermon). null borra el nombre.
curl -b cookies.txt -X PATCH localhost:8000/tanks/tank-1 \
  -H 'X-Requested-With: fermon' -H 'Content-Type: application/json' \
  -d '{"display_name": "Fermenter 1"}'
```

```json
{
  "id": "tank-1",
  "display_name": null,
  "first_seen_at": "2026-01-01T10:00:00Z",
  "active_batch": null,
  "open_alerts": 0,
  "latest": {
    "temperature": {"tank_id": "tank-1", "sensor_id": "tank-1-temp", "measurement": "temperature",
                    "value": 19.5, "unit": "celsius", "recorded_at": "2026-01-01T12:05:00Z"},
    "pressure": null,
    "alcohol": null
  }
}
```

`latest.<medición>` es `null` si el tanque aún no reportó esa medición. `active_batch` es el resumen
del lote activo del tanque (ver [Lotes](#lotes)) o `null`. `open_alerts` es la cantidad de alertas
sin resolver (`open` + `acknowledged`) del tanque (ver [Alertas](#alertas)). Los errores usan la forma
unificada `{"detail": [{"field", "message"}]}` (`404` para un tanque desconocido, `422` para un
`tank_id` en blanco). El nombre se recorta y debe tener de 1 a 64 caracteres (`422` sobre
`display_name` si queda vacío, es más largo o llega un campo desconocido); un `viewer` o `brewer` recibe `403`. Gana la última escritura
(el nombre no tiene versión) y la primera lectura de un tanque nunca pisa un nombre ya puesto. Todos los instantes se devuelven en UTC.

### CORS

`CORS_ORIGINS` define los orígenes del navegador autorizados a llamar a la API (solo `GET`, `POST`,
`PATCH`, `PUT` y `DELETE`, **con credenciales**: el navegador envía la cookie de sesión). Los encabezados
permitidos son `Content-Type`, `X-Requested-With` y `X-Device-Key`. Acepta una lista separada por comas o un
arreglo JSON; por defecto `http://localhost:5173,http://localhost:3000`. Debe listar orígenes explícitos:
`*` se rechaza al arrancar, porque los navegadores no admiten `*` junto con credenciales:

```sh
CORS_ORIGINS=https://panel.example.com,http://localhost:5173 docker compose up -d api
```

## Usuarios y sesiones

La API tiene usuarios con roles y sesiones del lado del servidor. Todo exige iniciar sesión (ver
[Autorización](#autorización)).

| Rol | Permisos |
| --- | --- |
| `admin` | Todo, incluidas la gestión de usuarios y la configuración de planta (renombrar tanques) |
| `brewer` | Crear, editar, iniciar y finalizar lotes; reconocer alertas; crear perfiles y especificaciones de calidad; registrar análisis de laboratorio; descargar reportes |
| `viewer` | Solo lectura (tanques, lecturas, lotes, alertas, perfiles, análisis) y descarga de reportes |

Las contraseñas se guardan con Argon2id y deben tener al menos 10 caracteres. No hay registro
abierto: el primer administrador se crea por comando y los demás los crea un admin con una contraseña
temporal (el usuario queda con `must_change_password: true` hasta que la cambia).

```sh
# La contraseña nunca va por argumentos ni queda en el historial del shell: se lee sin eco y se
# pasa al contenedor solo por nombre (`-e VAR`); o se omite y el comando la pide con `-it`.
read -rs FERMON_ADMIN_PASSWORD; export FERMON_ADMIN_PASSWORD
docker compose run --rm -e FERMON_ADMIN_PASSWORD api \
  python -m fermon.identity.create_admin --email admin@example.com --name "Admin"
```

El comando falla si el email ya existe. Los emails se normalizan a minúsculas y son únicos sin
distinguir mayúsculas.

**Entrar en la interfaz web.** Con el primer admin creado, abre `http://localhost:5173`: sin sesión la UI
muestra `/login` (email y contraseña) y, tras entrar, vuelve a la página pedida. El admin crea al resto en
*Users* (rol y contraseña temporal); esa persona debe cambiarla en su primer ingreso (`/account/password`,
también accesible desde el menú de la cabecera, donde está *Sign out*). Un `viewer` solo ve datos; `brewer`
y `admin` pueden crear y editar lotes y reconocer alertas; *Users* solo aparece para `admin`. En desarrollo
la UI (`localhost:5173`) y la API (`localhost:8000`) son del mismo sitio para el navegador (las cookies no
distinguen puertos), así que la cookie `SameSite=Lax` viaja también al WebSocket.

| Endpoint | Descripción |
| --- | --- |
| `POST /auth/login` | `{email, password}` → `200 {user}` y cookie `fermon_session`; `401` genérico si falla; `429` con `Retry-After` tras demasiados fallos |
| `POST /auth/logout` | `204`, revoca la sesión y borra la cookie (idempotente) |
| `GET /auth/me` | `200 {user}` o `401` |
| `POST /auth/password` | `{current_password, new_password}` → `204`; cierra las demás sesiones del usuario |
| `GET /users`, `POST /users` | Listar / crear usuarios (`POST` → `201`); solo `admin` |
| `PATCH /users/{id}` | `{version, role?, active?, display_name?}`; `409` si la versión quedó vieja o si se intenta degradar o desactivar al último admin |
| `POST /users/{id}/reset-password` | `{temporary_password}` → `204`; cierra todas las sesiones del usuario |

Sin sesión las rutas de usuarios responden `401`; con un rol insuficiente, `403`. El usuario nunca
incluye el hash de la contraseña.

La cookie `fermon_session` es `HttpOnly`, `SameSite=Lax` y `Path=/`. El navegador solo guarda un
token aleatorio; en la base se guarda su hash SHA-256 (tabla `sessions`), de modo que se puede
revocar y expira sola. Variables de entorno:

| Variable | Defecto | Descripción |
| --- | --- | --- |
| `SESSION_TTL_SECONDS` | `28800` (8 h) | Duración de la sesión y `Max-Age` de la cookie |
| `SESSION_COOKIE_SECURE` | `false` | Marca la cookie como `Secure`; activarlo detrás de HTTPS (con `false` el arranque avisa con un WARNING) |
| `LOGIN_MAX_FAILURES_PER_ACCOUNT` | `5` | Fallos de login permitidos por email dentro de la ventana |
| `LOGIN_MAX_FAILURES_PER_IP` | `20` | Fallos de login permitidos por IP del cliente dentro de la ventana |
| `LOGIN_THROTTLE_WINDOW_SECONDS` | `900` | Ventana deslizante del límite; pasado ese tiempo se puede reintentar |

Mientras un usuario tiene contraseña temporal (`must_change_password: true`) toda ruta autenticada
responde `403` (campo `password`), salvo `GET /auth/me`, `POST /auth/password` y `POST /auth/logout`;
al cambiar la contraseña se limpia la marca. El límite de intentos de login es por proceso (memoria):
vale para una sola instancia de la API; un login correcto reinicia el contador de la cuenta, no el de
la IP. Detrás de un proxy la IP vista es la del proxy.

## Autorización

Todo exige una sesión válida, salvo `GET /health`, `POST /auth/login`, `POST /auth/logout` (idempotente) y la
documentación de FastAPI (`/docs`, `/redoc`, `/openapi.json`). Sin sesión la respuesta es `401`, con la
forma unificada `{"detail": [{"field", "message"}]}`; con un rol insuficiente, `403`. Una prueba recorre
todas las rutas de la aplicación y falla si alguna nueva queda sin protección.

| Acción | `viewer` | `brewer` | `admin` |
| --- | :---: | :---: | :---: |
| Leer tanques, lecturas, lotes, alertas, perfiles y análisis; `POST /quality-profiles/{id}/evaluate` | sí | sí | sí |
| Descargar reportes de lote (`/batches/{id}/report.pdf`, `.csv`) | sí | sí | sí |
| Crear/editar/iniciar/finalizar lotes (`/batches`) | no | sí | sí |
| Reconocer alertas (`POST /alerts/{id}/acknowledge`) | no | sí | sí |
| Crear perfiles de calidad y `PUT`/`DELETE` de especificaciones | no | sí | sí |
| Registrar análisis de laboratorio | no | sí | sí |
| Gestionar usuarios (`/users`) | no | no | sí |

Las reglas viven en `fermon.identity.domain.role` (`can_write_batches`, …) y se aplican como dependencias
de las rutas; los `GET` solo piden una sesión.

**Iniciar sesión con curl.** La cookie `fermon_session` se guarda con `-c` y se envía con `-b`:

```sh
curl -c cookies.txt -X POST localhost:8000/auth/login \
  -H 'X-Requested-With: fermon' -H 'Content-Type: application/json' \
  -d '{"email": "admin@example.com", "password": "..."}'
curl -b cookies.txt localhost:8000/tanks
curl -b cookies.txt -X POST localhost:8000/batches/<id>/start -H 'X-Requested-With: fermon'
```

**CSRF.** Las peticiones que modifican (`POST`, `PUT`, `PATCH`, `DELETE`), incluidas `/auth/login`,
`/auth/logout` y `/auth/password`, deben llevar el encabezado `X-Requested-With: fermon` (valor exacto);
sin él la respuesta es `403` con `field: "X-Requested-With"`. Un formulario o una imagen de otro sitio no
puede añadir ese encabezado, y un `fetch` entre sitios que lo añade exige un preflight de CORS que solo
pasan los orígenes de `CORS_ORIGINS`. Se suma a la cookie `SameSite=Lax`. Solo `POST /readings` queda
exento (no usa cookie).

**Ingesta HTTP de dispositivos.** `POST /readings` no usa sesión de usuario: exige el encabezado
`X-Device-Key` con una de las claves de `DEVICE_API_KEYS` (lista separada por comas; se compara en tiempo
constante). Sin clave o con una clave incorrecta responde `401` (`field: "X-Device-Key"`). Por defecto
`DEVICE_API_KEYS` está vacía: la ingesta HTTP queda desactivada (siempre `401`) y el arranque avisa con un
WARNING. La ingesta por MQTT no cambia. Compose pasa la variable al servicio `api`:

```sh
DEVICE_API_KEYS=clave-del-sensor-1,clave-del-sensor-2 docker compose up -d api
curl -X POST localhost:8000/readings -H 'X-Device-Key: clave-del-sensor-1' -H 'Content-Type: application/json' \
  -d '{"tank_id": "tank-1", "sensor_id": "probe-a", "measurement": "temperature", "value": 18.5, "unit": "celsius", "recorded_at": "2026-01-01T10:00:00Z"}'
```

**WebSockets.** `/ws/tanks/{tank_id}` y `/ws/alerts` exigen la cookie de sesión en el apretón de manos (los
navegadores la envían solos). Sin sesión válida, o con contraseña temporal pendiente, se acepta y se cierra
con el código `4401`; un `Origin` fuera de `CORS_ORIGINS` se cierra con `4403` (se evalúa antes que la
sesión, porque los navegadores envían cookies también desde otros sitios). Un cliente sin `Origin` (script) se
acepta si la sesión es válida. Cualquier rol puede escuchar. Los códigos de cierre están en
[Tiempo real](#tiempo-real-websocket).

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
curl -X POST localhost:8000/batches -b cookies.txt -H 'X-Requested-With: fermon' -H 'Content-Type: application/json' -d '{
  "tank_id": "tank-1", "beer_name": "Pale Ale", "style": "APA", "template": "ale",
  "targets": {"temperature_max": 22.0}, "expected_end": "2026-02-01T00:00:00Z"
}'
curl -X POST localhost:8000/batches/<id>/start -b cookies.txt -H 'X-Requested-With: fermon'
curl -X PATCH localhost:8000/batches/<id> -b cookies.txt -H 'X-Requested-With: fermon' -H 'Content-Type: application/json' -d '{"notes": "dry hop"}'
curl -X POST localhost:8000/batches/<id>/finish -b cookies.txt -H 'X-Requested-With: fermon'
```

`GET /tanks` y `GET /tanks/{id}` incluyen `active_batch` (`id`, `beer_name`, `style`, `targets`,
`started_at`, `expected_end`, `quality_profile_id`), resuelto con una sola consulta para todos los
tanques listados.

Un lote puede asociarse a un **perfil de calidad** (ver más abajo) con `quality_profile_id`: se envía
al crear y se cambia o se quita (`null`) con `PATCH` mientras el lote no haya terminado. Si el perfil no
existe responde `404` con `field` `quality_profile_id`. Es opcional (migración `0007`, clave foránea a
`quality_profiles`); los lotes anteriores quedan sin perfil.

## Especificaciones de calidad

Además de los sensores, la calidad de la elaboración se controla con análisis de laboratorio en cuatro
etapas (`stage`): `brewhouse` (mosto frío), `maturation` (fin de reposo), `bright_beer` (filtración,
tanque de presión) y `packaged` (producto terminado). Un **perfil de calidad** (p. ej. "Pale lager")
guarda, por etapa y parámetro, una especificación de dos niveles:

- `acceptance`: límite de aceptación (`min` y/o `max`, inclusivos; un lado vacío es "sin límite").
- `internal` (opcional): rango interno de operación, que debe quedar dentro de `acceptance`.
- `target` (opcional): valor objetivo, dentro del rango más estrecho.

Un valor se evalúa como `in_spec` (dentro del interno), `warning` (fuera del interno pero dentro de la
aceptación) u `out_of_spec`; sin rango interno, la aceptación hace de interno. Los números deben estar
dentro del rango físico del parámetro (p. ej. pH 0–14). `<` y `≤` se guardan igual (inclusivos): la
diferencia es menor que la resolución de los instrumentos. Migración `0006`.

| Endpoint | Respuesta |
| --- | --- |
| `GET /quality-parameters` | Catálogo: `code`, `name`, `unit`, `minimum`, `maximum` (extractos °P, alcohol, pH, color EBC, amargor IBU, turbidez, O₂, CO₂, diacetilo, …) |
| `GET /quality-profile-templates` | Plantillas con especificaciones precargadas: `pale_lager` |
| `POST /quality-profiles` | `201` perfil vacío, o precargado con `template`; `409` (`name`) si ya existe uno con ese nombre sin distinguir mayúsculas |
| `GET /quality-profiles` | Perfiles por nombre, con sus especificaciones |
| `GET /quality-profiles/{id}` | Un perfil; `404` (`profile_id`) |
| `PUT /quality-profiles/{id}/specs/{stage}/{parameter}` | Crea o reemplaza la especificación; `422` nombra el campo inválido (p. ej. `internal.min`) |
| `DELETE /quality-profiles/{id}/specs/{stage}/{parameter}` | `204`; `404` (`spec`) si no existe |
| `POST /quality-profiles/{id}/evaluate` | Estado de cada valor de una etapa; `no_spec` si el perfil no especifica ese parámetro allí |

La plantilla `pale_lager` trae 29 especificaciones repartidas en las cuatro etapas (extracto, pH,
amargor, color, O₂ y FAN del mosto; extracto aparente, alcohol, diacetilo y turbidez al fin de reposo;
alcohol, CO₂, O₂ disuelto, turbidez y temperatura en filtración; además espuma, TPO y UP en producto
terminado). Son valores **ilustrativos** de manual para una lager rubia, pensados como punto de partida
para editar con `PUT`; no son las especificaciones de ninguna cervecería.

```sh
curl -X POST localhost:8000/quality-profiles -b cookies.txt -H 'X-Requested-With: fermon' -H 'Content-Type: application/json' \
  -d '{"name": "House lager", "template": "pale_lager"}'
curl -X POST localhost:8000/quality-profiles -b cookies.txt -H 'X-Requested-With: fermon' -H 'Content-Type: application/json' -d '{"name": "Pale lager"}'
curl -X PUT localhost:8000/quality-profiles/<id>/specs/bright_beer/ph -b cookies.txt -H 'X-Requested-With: fermon' -H 'Content-Type: application/json' \
  -d '{"acceptance": {"min": 4.15, "max": 4.65}, "internal": {"min": 4.25, "max": 4.55}}'
curl -X POST localhost:8000/quality-profiles/<id>/evaluate -b cookies.txt -H 'X-Requested-With: fermon' -H 'Content-Type: application/json' \
  -d '{"stage": "bright_beer", "values": {"ph": 4.6, "color": 6.1}}'
# -> ph: "warning", color: "no_spec"
```

Un lote se asocia a un perfil con `quality_profile_id` (ver Lotes), y sus análisis de laboratorio se
evalúan contra ese perfil (ver la sección siguiente).

## Análisis de laboratorio

Un análisis es una muestra de un lote en una etapa (`stage`): momento de muestreo (`sampled_at`, por
defecto ahora y nunca en el futuro), analista y notas opcionales, y uno o más valores por parámetro del
catálogo. Al registrarlo, cada valor se evalúa contra el perfil de calidad del lote y el estado se
**guarda** con el valor (`in_spec`, `warning`, `out_of_spec`, o `no_spec` si el perfil no especifica ese
parámetro en esa etapa o el lote no tiene perfil), junto con el perfil usado. Es el registro de calidad
de ese momento: editar después las especificaciones no cambia los análisis ya guardados. Un lote
`planned` todavía no tiene análisis (`409` en `status`); uno `active` o `finished` sí, porque la
filtración y el envasado ocurren después de la fermentación. Migración `0008`.

| Endpoint | Respuesta |
| --- | --- |
| `POST /batches/{id}/lab-analyses` | `201` con los resultados evaluados; `404` (`batch_id`); `409` (`status`) si el lote está planificado; `422` con el campo (`values.ph`, `values.<código desconocido>`, `sampled_at`, …) |
| `GET /batches/{id}/lab-analyses?stage=` | Análisis del lote, la muestra más antigua primero; filtro opcional por etapa |
| `GET /lab-analyses/{id}` | Un análisis; `404` (`analysis_id`) |

```sh
curl -X POST localhost:8000/batches/<id>/lab-analyses -b cookies.txt -H 'X-Requested-With: fermon' -H 'Content-Type: application/json' -d '{
  "stage": "brewhouse", "analyst": "M. Ruiz",
  "values": {"original_extract": 11.4, "ph": 5.6, "wort_oxygen": 7.0}
}'
# -> original_extract: "in_spec", ph: "out_of_spec", wort_oxygen: "warning" (con la plantilla pale_lager)
```

Todavía no se puede editar ni borrar un análisis (una corrección se registra como un análisis nuevo), y
los parámetros derivados por fórmula (p. ej. color = absorbancia × 25) se cargan ya calculados.

## Reportes

Cada lote `active` o `finished` se puede descargar como PDF o CSV; un lote `planned` responde `409` (`field:
"status"`) y uno desconocido `404` (`field: "batch_id"`). Cualquier rol con sesión puede descargarlos
(también `viewer`); el reporte es determinista, sin IA, y sale de los mismos datos que ven el panel y la API.

| Endpoint | Respuesta |
| --- | --- |
| `GET /batches/{id}/report.pdf` | `application/pdf`, A4, adjunto `batch-<cerveza>-<fecha>.pdf` |
| `GET /batches/{id}/report.csv` | `text/csv`, adjunto `batch-<cerveza>-<fecha>.csv` |

La fecha del nombre es la de generación (UTC). Un lote activo da un reporte **parcial**, marcado
«Partial (batch in progress)» y calculado hasta el momento de la descarga; uno finalizado cubre de
`started_at` a `finished_at`.

Desde la interfaz, el detalle de un lote `active` o `finished` muestra los enlaces «Download PDF» y
«Download CSV» (también para `viewer`; con un aviso de reporte parcial si el lote sigue activo). Son enlaces
normales, no `fetch`: el navegador envía la cookie de sesión y baja el archivo directamente.

**Contenido del PDF** (plantilla HTML con Jinja2, impresa con WeasyPrint; los gráficos son SVG en línea
generados en Python, sin JavaScript ni librerías de gráficos): datos del lote (cerveza, estilo, tanque,
estado, perfil de calidad, inicio, fin o fin esperado, duración), estadísticas por medición (lecturas, mín,
máx, promedio, primer y último valor, rango objetivo y % de tiempo en rango), gráficos de temperatura,
presión y ABV frente al esperado con el rango objetivo sombreado, alertas del lote (tipo, medición,
apertura, reconocimiento, resolución, duración y motivo) y análisis de laboratorio con el estado guardado
de cada valor. Pie con la fecha de generación y el número de página. El **CSV** es una sola tabla plana:
una sección de resumen del lote y una de estadísticas por medición (sin series, alertas ni análisis).

**Resolución.** Las estadísticas salen de los agregados de **1 minuto** (`readings_1m`), no de las lecturas
crudas: una fermentación de semanas son millones de muestras. Por eso `count` suma las lecturas, `min` y
`max` son exactos, el promedio se pondera por lecturas y «primer» y «último» valor son el promedio del
primer y del último minuto con datos. Los gráficos reducen cada serie a un máximo de 240 puntos (intervalos
iguales de minutos enteros, promedio ponderado).

**% de tiempo en rango.** Cada muestra (minuto) mantiene su valor hasta la siguiente y aporta
`min(tiempo hasta la siguiente muestra, REPORT_MAX_GAP_SECONDS)`; la última, hasta el fin del reporte con el
mismo tope. Un silencio mayor al tope (por defecto 600 s = 10 min) **no cuenta como en rango**, y tampoco
como tiempo observado: el porcentaje es «del tiempo observado». Está en rango si `mín <= valor <= máx` del
objetivo del lote (un límite ausente no acota). Sin objetivo, el % es `null` en el CSV y `-` en el PDF: es
el caso del alcohol, que solo muestra progreso.

**ABV frente al esperado.** Modelo lineal: 0 % al iniciar y `expected_final_abv` en `expected_end`, plano
después. Sin `expected_end` o sin `expected_final_abv` no se dibuja la curva esperada.

```sh
curl -b cookies.txt -OJ localhost:8000/batches/<id>/report.pdf
curl -b cookies.txt -OJ localhost:8000/batches/<id>/report.csv
```

`REPORT_MAX_GAP_SECONDS` (por defecto `600`) es el tope de silencio. El PDF necesita Pango y una fuente
del sistema: el `Dockerfile` los instala (`libpango-1.0-0`, `libpangoft2-1.0-0`, `libharfbuzz-subset0`,
`fonts-dejavu-core`) tanto en `dev` como en `prod`. Limitaciones: la alerta no guarda quién la reconoció,
así que el reporte solo muestra cuándo; la generación del PDF es síncrona en un hilo aparte y no se cachea.

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
segundos.

### API de alertas

| Método y ruta | Descripción |
| --- | --- |
| `GET /alerts` | Lista de alertas, la más reciente primero (por `opened_at`) |
| `GET /alerts/{id}` | Una alerta; `404` si no existe |
| `POST /alerts/{id}/acknowledge` | `open` → `acknowledged`; cuerpo opcional `{"version": n}` |

Filtros de `GET /alerts` (todos opcionales): `tank_id`, `batch_id`, `kind` (`out_of_range` o
`silent_sensor`), `status` (repetible: `?status=open&status=resolved`) y `limit` (1 a 500, por defecto
100). **Sin `status` solo se devuelven las alertas sin resolver** (`open` y `acknowledged`); para ver
las resueltas hay que pedirlas con `status=resolved`.

```json
{
  "id": "0b0c8f0e-...", "tank_id": "tank-1", "batch_id": "6f1d...",
  "kind": "out_of_range", "measurement": "temperature", "status": "acknowledged",
  "opened_at": "2026-01-01T12:05:00Z", "acknowledged_at": "2026-01-01T12:09:00Z",
  "resolved_at": null,
  "details": {"observed": 25.5, "bound": "above", "target_min": 18.0, "target_max": 21.0},
  "version": 2
}
```

- `acknowledged_at` se toma del reloj del servidor. Reconocer una alerta **ya reconocida** es
  idempotente: responde `200` con la alerta tal cual, sin escribir ni subir la versión.
- Errores con la forma unificada `{"detail": [{"field", "message"}]}`: `404` (`alert_id`) si la alerta
  no existe; `409` (`status`) si ya está resuelta; `409` (`version`) si el `version` enviado ya no es el
  vigente o si otra escritura se adelantó; `422` para filtros o cuerpo inválidos.

## Series agregadas

Para graficar no se piden lecturas crudas (una fermentación de 10 días a 1 lectura/s son cientos de
miles de puntos) sino agregados por cubo de tiempo. La migración `0003` crea dos *continuous
aggregates* de TimescaleDB: `readings_1m` (cubos de 1 minuto, sobre `readings`) y `readings_1h`
(cubos de 1 hora, jerárquico sobre `readings_1m`, así nunca relee las lecturas crudas).

```sh
curl -b cookies.txt 'localhost:8000/tanks/tank-1/readings/aggregated?bucket=1m&start=2026-01-01T12:00:00Z&end=2026-01-01T13:00:00Z'
curl -b cookies.txt 'localhost:8000/tanks/tank-1/readings/aggregated?bucket=1h&measurement=temperature&measurement=pressure&start=...&end=...'
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

`ws://localhost:8000/ws/tanks/{tank_id}` (requiere la cookie de sesión, ver [Autorización](#autorización)) envía cada lectura nueva del tanque como un mensaje de
texto JSON, con la misma forma que `ReadingOut` de la API REST (instantes en UTC):

```json
{"tank_id": "tank-1", "sensor_id": "tank-1-temp", "measurement": "temperature",
 "value": 19.5, "unit": "celsius", "recorded_at": "2026-01-01T12:05:00Z"}
```

Cómo funciona: al guardar una lectura **nueva** (no un duplicado), el adaptador de persistencia
ejecuta `pg_notify('fermon_readings', <json>)` en la misma transacción del `INSERT`. PostgreSQL
entrega la notificación solo al confirmar (`COMMIT`), así que el panel nunca ve datos que no estén
en la base. Tanto `POST /readings` (con `X-Device-Key`) como el ingestor MQTT pasan por ese adaptador. La API mantiene
una conexión dedicada con `LISTEN` y reparte cada mensaje a los clientes suscritos a ese tanque.

- Tanque desconocido o `tank_id` en blanco: el servidor acepta y cierra de inmediato con el código
  `4404` y un motivo. El `tank_id` se normaliza (espacios) igual que en REST.
- Códigos de cierre del WebSocket:

  | Código | Significado |
  | ------ | ----------- |
  | `1011` | Error interno: falló la consulta del tanque (p. ej. base de datos caída). El servidor acepta y cierra con el motivo `internal error` y registra el error. Reintente más tarde. |
  | `4401` | Sin sesión válida: falta la cookie `fermon_session`, expiró o fue revocada, o la cuenta tiene contraseña temporal pendiente. Se cierra antes de consultar el tanque. |
  | `4403` | Origen no permitido (ver abajo). |
  | `4404` | Tanque desconocido o `tank_id` en blanco. |

- Origen no permitido: si el encabezado `Origin` no está en `CORS_ORIGINS` se acepta el
  apretón de manos y se cierra de inmediato con `4403` y un motivo, para que el navegador lo
  observe (CORS no cubre WebSockets, por eso se valida aparte). Los clientes sin
  `Origin` (scripts, `websocat`) se aceptan si la sesión es válida: la comprobación de origen protege
  contra páginas de otros sitios que aprovechan la cookie del navegador; la autenticación es la sesión.
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
    async with websockets.connect('ws://localhost:8000/ws/tanks/tank-1',
            additional_headers={'Cookie': 'fermon_session=<valor de cookies.txt>'}) as ws:
        async for message in ws:
            print(message)
asyncio.run(main())"
```

### Alertas en vivo: `/ws/alerts`

`ws://localhost:8000/ws/alerts` envía **cada cambio de cualquier alerta** (de todos los tanques) como un
mensaje de texto JSON `{"type": "alert", "alert": <AlertOut>}`, con la misma forma de `AlertOut` de
`GET /alerts`. Llega un mensaje por revisión guardada: al abrirse, al reconocerse y al resolverse (así
que `alert.status` indica qué pasó).

```json
{"type": "alert", "alert": {"id": "0b0c8f0e-...", "tank_id": "tank-1", "status": "open", "...": "..."}}
```

Funciona igual que el WebSocket de lecturas: el adaptador de persistencia ejecuta
`pg_notify('fermon_alerts', <json>)` en la misma transacción de cada alta o actualización de alerta
(se entrega recién al `COMMIT`, dentro de un `SAVEPOINT`; un error de `NOTIFY` o un payload de más de
7500 bytes se registra y nunca hace fallar la escritura de la alerta). La API usa **la misma conexión de
escucha** para `fermon_readings` y `fermon_alerts`, con la misma reconexión y comprobación de salud.

| Código de cierre | Significado |
| ---------------- | ----------- |
| `1011` | Error interno: no se pudo suscribir al flujo de alertas. Se acepta y se cierra con el motivo `internal error`. |
| `4401` | Sin sesión válida (mismas reglas que `/ws/tanks/{id}`). |
| `4403` | Origen no permitido: mismas reglas de `CORS_ORIGINS` que `/ws/tanks/{id}`. |

- Mejor esfuerzo, sin repetición: las alertas que cambian mientras el cliente estaba desconectado, o
  mientras la API había perdido su conexión de escucha, no se reenvían. Al (re)conectar hay que
  completar con `GET /alerts`.
- Cliente lento: cola acotada de 100 mensajes por suscriptor; si se llena se descarta el más antiguo.
- Los mensajes que envía el cliente se ignoran.

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


### Lotes en la UI

El encabezado tiene la navegación "Tanks" / "Batches". Rutas (cargadas bajo demanda, fuera del
bundle principal): `/batches` (lista con filtros `?tank_id=` y `?status=`; tabla en escritorio,
tarjetas en móvil), `/batches/new` (formulario; `?tank=<id>` preselecciona el tanque) y
`/batches/:batchId` (edición mientras está `planned` o `active`, solo lectura al finalizar; botón
"Start batch" y "Finish batch" con confirmación).

La plantilla (`ale`, `lager`, `custom`) precarga los rangos desde `GET /batch-templates`; el
formulario valida igual que el backend (obligatorios, mín < máx) pero siempre muestra los 422 del
servidor junto al campo correspondiente. Las ediciones envían la `version` del lote: un 409 muestra
"This batch changed since you opened it" con un botón para recargar. Al crear, iniciar o finalizar
se invalidan los lotes y los tanques, de modo que la tarjeta y el detalle del tanque muestran el
lote activo (o "No active batch" / "Start a batch") y los gráficos sombrean el rango objetivo de
temperatura y presión (`markArea`).

### Alertas en la UI

El encabezado suma el enlace "Alerts" con un contador de alertas sin resolver. La fuente de verdad
del contador es la suma de `open_alerts` de `GET /tanks` (la misma consulta de la vista general, sin
tope de paginación y coherente con las tarjetas). Una tarjeta con `open_alerts > 0` muestra un
indicador que enlaza a `/alerts?tank=<id>`, y el detalle del tanque lista sus alertas activas.

`/alerts` (carga bajo demanda): filtros de estado (Open / Acknowledged / Resolved, multiselección;
por defecto Open + Acknowledged, siempre queda al menos uno), tanque (`?tank=`) y tipo (`?kind=`),
las más nuevas primero. "Acknowledge" envía la `version` vista: un 409 por `status` muestra "already
resolved" y un 409 por `version` refresca la lista y pide reintentar. Un único WebSocket
`/ws/alerts`, montado una sola vez en el shell, inserta/reemplaza cada revisión en las listas en
caché (según los filtros de cada una, ignorando versiones más antiguas); como `open_alerts` solo
cambia cuando una alerta se abre o se resuelve, esos eventos (no los reconocimientos) vuelven a pedir
los tanques, agrupados en 250 ms. En cada reconexión se invalidan las listas de alertas y los tanques.

### Pruebas e2e (Playwright)

Corren contra el stack real con el simulador publicando, en Chromium de escritorio y en un
viewport móvil (Pixel 7). El navegador vive dentro de la red de Compose (imagen oficial
`mcr.microsoft.com/playwright:v1.64.1-noble`, misma versión que `@playwright/test`), así que no se
instala ningún navegador en el equipo anfitrión.

```sh
docker compose run --rm api uv run alembic upgrade head   # primero las migraciones
# Umbrales de alerta cortos para el ingestor (los valores por defecto son 300/120/600/60 s):
export ALERT_OUT_OF_RANGE_SECONDS=15 ALERT_RESOLVE_SECONDS=10 ALERT_SILENT_SECONDS=20 ALERT_SILENT_CHECK_INTERVAL_SECONDS=3
docker compose --profile simulator --profile e2e up -d timescaledb mosquitto api ingestor simulator frontend-e2e
docker compose run --rm e2e                                # npx playwright test
docker compose --profile simulator --profile e2e down
```

Las alertas reales tardan minutos, así que el `ingestor` lee sus umbrales `ALERT_*` del entorno del
shell (en `docker-compose.yml` con los valores de producción como defecto: sin exportarlas nada
cambia). Si el `ingestor` ya estaba corriendo con otros valores, `up -d` lo recrea al detectar el
cambio de entorno; no hace falta un segundo ingestor. `frontend/e2e/batches-alerts.spec.ts` crea sus
propios lotes en `tank-1` (a veces por la API), los finaliza al terminar y corre en serie y solo en
el proyecto de escritorio, porque un tanque admite un único lote activo y el proyecto móvil
competiría por él. Para volver a los umbrales normales: `unset` las variables y `up -d ingestor`.

La API exige sesión, así que el servicio `e2e-admin` (perfil `e2e`) crea un administrador
(`e2e-admin@example.com`, contraseña `E2E_ADMIN_PASSWORD`, por defecto `e2e-admin-password`; sin contraseña
temporal) antes de las pruebas; es repetible (si ya existe lo informa y sigue). El `globalSetup` entra una vez
con él y guarda la sesión en `frontend/e2e/.auth/admin.json` (ignorado por git), que usan todos los specs
(`storageState`); `auth.spec.ts` entra a mano. La cookie es `SameSite=Lax`, y `frontend-e2e` y `api` son
sitios distintos para el navegador, así que `frontend-e2e` sirve la API en `/api` de su propio origen (proxy
de Vite hacia `API_PROXY_TARGET`, `VITE_API_URL=/api`); los ayudantes de API de los specs usan la misma ruta.

Prerrequisitos: migraciones aplicadas y simulador activo (las pruebas esperan tank-1 y tank-2 con
lecturas). El servicio `e2e` espera a que `api` y `frontend-e2e` respondan (healthchecks) y un
`globalSetup` espera hasta 90 s a que existan lecturas de tank-1 y tank-2; si no, falla con un mensaje
claro. `frontend-e2e` es una copia de `frontend`
con `VITE_API_URL=/api` (proxy de Vite hacia `http://api:8000`, ver arriba); el `frontend`
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

### Perfiles de calidad en la UI

La navegación incluye "Quality" (todos los roles) hacia `/quality-profiles`: lista de perfiles con su número de
especificaciones y, para `admin`/`brewer`, "New profile" (nombre y plantilla opcional o perfil en blanco).
`/quality-profiles/:id` agrupa las especificaciones por etapa (mosto frío, maduración, cerveza brillante,
envasado) con aceptación, rango interno y objetivo; `admin`/`brewer` pueden agregar, editar y borrar (con
confirmación); el `viewer` solo lee. Los errores `422`/`409` del servidor se muestran junto a su campo.

El formulario de lote (crear y editar) ofrece "Quality profile" (opcional, "None" por defecto; deshabilitado en
lotes terminados) y el detalle muestra el perfil enlazado. Debajo, "Lab analyses" lista los análisis por etapa con
resumen ("1 out of spec, 1 warning") y cada valor con su estado (In spec verde, Warning ámbar, Out of spec rojo,
No spec gris, siempre con texto). `admin`/`brewer` registran uno con "Record analysis" (etapa, fecha de muestreo
sin futuro, analista, notas y valores validados contra los límites físicos del catálogo; sugiere los parámetros
del perfil para la etapa); un lote planificado solo muestra una nota y el `viewer` solo lee.
