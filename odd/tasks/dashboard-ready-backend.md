# Feature: dashboard-ready-backend

## Objetivo
Dejar el backend listo para que un dashboard web responsive lo consuma: listar tanques con su
estado actual, graficar series agregadas y recibir lecturas nuevas en tiempo real.

## Problema y por qué
La base actual solo ingesta y devuelve lecturas crudas por rango. Un dashboard necesita:
- saber qué tanques existen y su última lectura (vista general);
- series agregadas (una fermentación de 10 días a 1 lectura/s son cientos de miles de puntos);
- actualizaciones en vivo sin polling;
- CORS para llamar a la API desde otro origen.

## Alcance autorizado
Backend (`backend/`), `docker-compose.yml` y README. Fuera de alcance: lotes de fermentación,
alertas, autenticación, retención (features posteriores), frontend.

## Decisiones de diseño
- **Tanques auto-registrados**: tabla `tanks` (`id`, `display_name` opcional, `first_seen_at`); la
  ingesta registra el tanque si no existe. Los lotes y alertas futuros se cuelgan de esta entidad.
- **Agregados con continuous aggregates de TimescaleDB** en buckets de 1 minuto y 1 hora (avg, min,
  max, count por tanque, sensor y medición), con agregación en tiempo real para incluir datos recientes.
- **Tiempo real con PostgreSQL LISTEN/NOTIFY**: el ingestor notifica solo lecturas efectivamente
  guardadas (nuevas, no duplicadas); la API escucha y reenvía por WebSocket. Así el dashboard nunca
  muestra datos que no estén en la base.
- **CORS** con orígenes configurables por variable de entorno.

## Restricciones
- Strict TDD, runner `docker compose run --rm api uv run pytest`.
- Entrega: un commit por funcionalidad terminada y corregida (T1, T2, T3), un solo PR. Flujo por
  funcionalidad: implementar → commit → revisión RDD → correcciones (amend) → push.

## Tareas
- [x] T1 — CORS + tanques: tabla `tanks` con migración, auto-registro en la ingesta,
  `GET /tanks` (con última lectura por medición) y `GET /tanks/{tank_id}`.
- [x] T2 — Series agregadas: continuous aggregates 1m/1h + `GET /tanks/{tank_id}/readings/aggregated`.
- [x] T3 — Tiempo real: NOTIFY desde el ingestor, LISTEN en la API, WebSocket `/ws/tanks/{tank_id}`.
- [x] T4 — PR.

## Criterios de aceptación
- Con el simulador corriendo, `GET /tanks` lista tank-1 y tank-2 con sus últimas lecturas.
- `GET .../aggregated?bucket=1m` devuelve puntos agregados del rango pedido.
- Un cliente WebSocket recibe las lecturas nuevas de su tanque segundos después de publicarse.

## Pendientes heredados (de `ingestor-transient-errors`, no incluidos)
- La espera del esquema no es cancelable si `engine.connect()` queda colgado.
- El test unitario de revisión conocida pero vieja se saltea con una sola migración.

## Progreso
- Rama `feat/dashboard-ready-backend` desde `main` (`d4eeea9`). TimescaleDB 2.31.0.

- T1 completada (ruta delegada, un escritor). CORS (`CORS_ORIGINS`, GET/POST), dominio `Tank`,
  `TankNotFoundError` → 404 con formato unificado, migración `0002` con backfill desde `readings`,
  auto-registro en la ingesta (`IngestReading(readings, tanks)`, dos transacciones: primero el tanque),
  `ListTanks`/`GetTank` con la última lectura por medición (LATERAL por par tanque/medición sobre el
  índice `(tank_id, recorded_at DESC)`). Sin FK desde `readings` (hypertable). Evidencia TDD: RED
  `AttributeError ... cors_origins`, `ImportError ... GetTank`, `ImportError ... get_get_tank`,
  `UndefinedTableError: relation "tanks"`, drift `add_table tanks`; GREEN `218 passed`; unitarios
  `192 passed`. ruff/format/mypy OK. Smoke dev: `/tanks` con tank-1 y tank-2, 404 para `nope`,
  preflight CORS permitido 200 y rechazado 400. Spot check del orquestador: 218 passed.
  Tamaño: 39 archivos, +1044/−48 (mayormente tests).

- Revisión RDD de T1 (`d4eeea9` → `3aafc81`, 1103 líneas, medio): aprobada por el usuario,
  **aprobada** y reconocida. Hallazgos corregidos inline antes del push (amend):
  - WARNING `R3-first-seen-at-arrival-order`: `ensure` usa `ON CONFLICT DO UPDATE SET first_seen_at =
    LEAST(...)`, así gana la lectura más antigua aunque lleguen fuera de orden (igual que el backfill).
  - SUGGESTION `R3-latest-tie-nondeterministic`: desempate por `sensor_id DESC` en la última lectura.
  RED observado: 3 failed (2 de integración + el fake); GREEN `221 passed`; ruff/mypy OK.

- Re-revisión RDD del T1 corregido (`924e075`, 1155 líneas, medio): aprobada por el usuario,
  **aprobada** y reconocida. Hallazgos corregidos inline con TDD:
  - WARNING `R3-ensure-unconditional-update`: el upsert solo reescribe si el `seen_at` nuevo es
    estrictamente anterior (`WHERE excluded.first_seen_at < tanks.first_seen_at`); RED: el `xmin`
    de la fila cambiaba con una lectura posterior.
  - SUGGESTION `R3-fake-latest-tie-divergence`: el fake desempata igual que SQL (`sensor_id`); RED observado.
  - SUGGESTION `R3-cors-client-not-closed`: fixture async con cierre del cliente.
  GREEN `223 passed`; ruff/format/mypy OK.
- Revisión RDD de esas correcciones (50 líneas, medio): aprobada por el usuario, **aprobada** y
  reconocida. WARNING `R3-lock-claim` corregido (el comentario ahora aclara que Postgres igual bloquea
  la fila; solo se evita escribir una nueva versión). SUGGESTION `R3-null-first-seen` no aplica
  (`first_seen_at` es `NOT NULL`).
- Entrega: T1 enmendado y `push --force-with-lease` autorizado por el usuario.

- T2 completada (ruta delegada, un escritor). Migración `0003`: continuous aggregates `readings_1m`
  y `readings_1h` (jerárquico sobre `readings_1m`), columnas `sum_value/min/max/sample_count` para
  que el promedio horario sea ponderado exacto; agregación en tiempo real (`materialized_only=false`);
  políticas 1m (2 h / 1 min / cada 1 min) y 1h (3 días / 1 h / cada 30 min); `autocommit_block()`;
  downgrade quita las políticas antes de los DROP (evita una carrera con el job de refresh).
  Agrega todos los sensores de una misma medición. `AggregationBucket`, `AggregatedPoint`, guard de
  10 000 puntos (`TooManyPointsError` → 422), `ListAggregatedReadings`,
  `GET /tanks/{tank_id}/readings/aggregated?bucket&start&end&measurement`. Limitación documentada: una
  lectura tardía en un bucket ya materializado no aparece hasta el próximo refresh (test de
  caracterización). Evidencia TDD: RED `ImportError ... ListAggregatedReadings`,
  `... get_list_aggregated_readings`, 7 × `AttributeError ... aggregated`, migración sin caggs; GREEN
  `249 passed` (6 corridas seguidas). Con las correcciones de T1 integradas: `251 passed`;
  ruff/format/mypy OK. Smoke dev: 1m y 1h devuelven puntos (p. ej. avg 19.05, count 15).

- Revisión RDD de T2 (`552f800` → `7881b96`, 1001 líneas, medio): aprobada por el usuario,
  **aprobada** y reconocida. Única SUGGESTION `R3-policy-params-unasserted` corregida: el test de la
  migración ahora afirma las ventanas de las políticas (1h: 3 days / 01:00:00 / 30 min; 1m:
  02:00:00 / 00:01:00 / 1 min). Es de caracterización (la migración ya era correcta). Hallazgo:
  en TimescaleDB 2.31 los jobs de refresh reportan el nombre de la vista, no la hypertable interna.
  `251 passed`; ruff/format OK.

- Revisión RDD conjunta de T1+T2 (`d4eeea9` → `3c81e9d`, 2201 líneas, medio; pedida por el hook tras
  el amend de T2): aprobada por el usuario, **aprobada** y reconocida. Sugerencias no bloqueantes
  (trabajo futuro, solo tests):
  - `R3-ensure-failure-path-unproved`: falta test de falla transitoria en el upsert del tanque durante la ingesta.
  - `R3-duplicate-measurement-param-untested`: falta test HTTP con `measurement` repetido en el endpoint agregado.
- T3 completada (ruta delegada, un escritor). `pg_notify('fermon_readings', ...)` en la misma
  transacción del insert, solo si se insertó (HTTP y MQTT notifican). `infrastructure/realtime`:
  `ReadingBroadcaster` (una conexión asyncpg con `add_listener`, reconexión 1→30 s, cola por cliente
  de 100 con descarte del más viejo, payload malformado descartado con WARNING), protocolo
  `ReadingFeed`. WebSocket `/ws/tanks/{tank_id}`: 4404 tanque inexistente, 4403 origen no permitido
  (CORS no cubre WebSockets; sin `Origin` se permite). Brecha documentada: notificaciones durante una
  desconexión del listener se pierden; el cliente rellena vía REST. Evidencia TDD: RED
  `ModuleNotFoundError ... realtime`, `ImportError ... get_reading_feed`, 3 integración con
  `TimeoutError` (nada notificado); `test_lifespan.py` de caracterización. GREEN `281 passed`;
  unitarios `240 passed`; ruff/format/mypy OK. Smoke dev: 5 mensajes recibidos por WebSocket,
  `tank-nope` → 4404, origen ajeno → HTTP 403. Spot check del orquestador: 281 passed.

- Revisión RDD de T3 (`3c81e9d` → `07d154a`, 907 líneas, medio) y de la rama completa (`d4eeea9` →
  `07d154a`, 3100 líneas, pedida por el hook): ambas aprobadas por el usuario, **aprobadas** y
  reconocidas. Hallazgos corregidos dentro de T3 antes del push (ruta delegada):
  - WARNING listener muere en silencio → `except Exception` con ERROR + backoff; `stop()` no re-lanza.
  - WARNING lookup de tanque con falla de infraestructura → cierre 1011 `internal error` (tabla de
    códigos 1011/4403/4404 en README).
  - Conexión medio caída → `SELECT 1` cada 30 s con timeout de 5 s; si falla, reconecta.
  - NOTIFY nunca tumba la ingesta → límite de 7500 bytes (si se excede, se omite con WARNING) y
    `pg_notify` dentro de un SAVEPOINT (si falla, se loguea y la lectura se guarda igual).
  - Tests deterministas: evento `ready` del broadcaster, sincronización del contador de suscriptores,
    y tests de orden de commit (2 de caracterización de la garantía de PostgreSQL + 1 del camino del
    repositorio: `insert → notify → commit` en una misma conexión).
  Evidencia TDD: RED `ValueError('boom')` mataba la tarea, `ConnectionError` escapaba de la ruta,
  `TypeError health_interval`, `AttributeError MAX_NOTIFY_PAYLOAD_BYTES`, `AttributeError ready`.
  GREEN `292 passed` (3 corridas seguidas); unitarios `246 passed`; ruff/format/mypy OK. Spot check
  del orquestador: 292 passed y WebSocket en vivo recibiendo lecturas de tank-1.
- Entrega: T3 enmendado (sin push previo) y push; PR.

- Revisión RDD del T3 final (`82fb4b1`, 1223 líneas): aprobada por el usuario, **aprobada** y
  reconocida. Corregido dentro de T3 (amend + `push --force-with-lease` autorizado por el usuario):
  - WARNING `R3-stop-blocks-on-inflight-connect`: `stop()` espera `stop_grace` (1 s) y luego cancela.
  - WARNING `R3-4403-not-observable-pre-accept`: se acepta y se cierra con 4403 para que el navegador
    lo vea; README corregido. Smoke con cliente real: `close 4403 origin not allowed`.
  - SUGGESTION `R3-half-open-close-unbounded`: `close()` con timeout (5 s) y `terminate()` de respaldo.
  RED: 3 failed (2 por parámetros nuevos inexistentes, sin reproducir el cuelgue en sí; 1 de
  comportamiento del 4403). GREEN `294 passed` (2 corridas); ruff/format/mypy OK.
- Revisión RDD de esas correcciones (113 líneas): aprobada por el usuario, **aprobada** y reconocida.
  WARNING `R3-stop-cancel-skips-terminate-fallback` corregido inline: si `stop()` cancela un `close()`
  colgado, igual se llama a `terminate()` antes de propagar la cancelación. RED `assert False`
  (`terminated`), GREEN `295 passed`.
- La revisión de la rama completa (3414 líneas) no corrió: `lens_context_budget_exceeded`; cada
  commit se revisó por separado. Por acuerdo con el usuario no se abre otra ronda.

## Trabajo futuro
- Test de falla transitoria en el upsert del tanque durante la ingesta (`R3-ensure-failure-path-unproved`).
- Test HTTP con `measurement` repetido en el endpoint agregado (`R3-duplicate-measurement-param-untested`).
- Heredados: espera del esquema no cancelable con `engine.connect()` colgado; test BEHIND salteado.
- Notificaciones perdidas mientras el listener está desconectado (el cliente rellena por REST).

## Próximo paso
PR `feat/dashboard-ready-backend` → `main` (merge: decisión del usuario).
