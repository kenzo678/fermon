# Feature: batches-and-alerts

## Objetivo
Pasar de monitorear lecturas a gestionar fermentaciones: lotes con rangos objetivo por tanque y
alertas cuando la fermentación se sale de esos rangos o un sensor deja de reportar.

## Problema y por qué
Hoy el sistema solo rechaza valores físicamente imposibles. La cervecería necesita saber qué cerveza
hay en cada tanque, con qué rangos objetivo, y enterarse cuando algo se desvía. Además, la feature
siguiente (reportes deterministas por lote, sin IA) depende de estos datos.

## Alcance aprobado por el usuario
### Lotes
- Datos: nombre de la cerveza, estilo, tanque, fecha de inicio, fecha estimada de fin, notas.
- Estados: planificado → activo → finalizado. Un solo lote activo por tanque.
- Plantillas por estilo: ale (18–21 °C) y lager (8–12 °C); precargan rangos editables por lote.
### Rangos objetivo (por lote)
- Temperatura: mín y máx (°C). Presión: máx (bar), mín opcional.
- Alcohol: ABV final esperado (%) — para mostrar progreso, no alerta.
### Alertas
- Fuera de rango: temperatura o presión fuera del objetivo durante más de 5 minutos seguidos.
- Sensor silencioso: sin lecturas de un tanque con lote activo por más de 10 minutos.
- Ciclo de vida: abierta → reconocida → resuelta (automática al volver al rango y sostenerse).
- Evaluación en el backend: al ingresar cada lectura + chequeo periódico de sensores silenciosos.
### Notificación
- Solo en el dashboard: contador, lista y aviso en tiempo real por WebSocket.
### Interfaz
- Formulario de lote (crear, editar, iniciar, finalizar); tarjeta del tanque con lote activo e
  indicador de alerta; bandas de rango objetivo en los gráficos; página de alertas con filtros y
  "Reconocer".
### Fuera de alcance
- Usuarios y autenticación; historial y reportes (feature siguiente: generador de reportes
  determinista por lote, PDF + CSV, sin IA — dejar previstos los datos que va a necesitar).

## Restricciones
- Strict TDD. Runners: backend `docker compose run --rm api uv run pytest`; frontend
  `docker compose run --rm --no-deps frontend npm test`; e2e `docker compose run --rm e2e`.
- Código, identificadores, comentarios y textos de UI en inglés; planificación en español.
- Entrega: un commit por funcionalidad terminada, revisada y corregida; push recién después de la
  revisión y sus correcciones; lockfiles en commit propio. Dos PRs: backend (T1–T2) y frontend (T3–T5).

## Tareas
- [x] T1 — Backend de lotes: dominio `Batch` (estados, rangos, plantillas por estilo), migración,
  repositorio, casos de uso (crear, editar, iniciar, finalizar, listar, lote activo por tanque), API
  REST; `GET /tanks` incluye el lote activo.
- [x] T2a — Núcleo del motor de alertas (reglas, ciclo de vida, persistencia, evaluación).
- [x] T2b — API de alertas y aviso en tiempo real.
- [x] T2 (original) — Motor de alertas: reglas fuera de rango sostenido (5 min) y sensor silencioso (10 min),
  ciclo de vida abierta/reconocida/resuelta, persistencia, API (`GET /alerts`, reconocer), aviso en
  tiempo real por WebSocket. PR del backend.
- [ ] T3 — UI de lotes: formulario (con plantillas), estados, lote activo en la tarjeta y en el
  detalle, bandas de rango objetivo en los gráficos.
- [ ] T4 — UI de alertas: contador, página con filtros, "Reconocer", indicador en la tarjeta, aviso
  en vivo.
- [ ] T5 — e2e de lotes y alertas (con el simulador forzando una desviación); PR del frontend.

## Criterios de aceptación
- Crear un lote activo en tank-1 con rango de temperatura que el simulador no cumple genera una
  alerta abierta en menos de ~6 minutos simulados, visible en el dashboard en vivo; al volver al
  rango se resuelve sola.
- Detener el simulador de un tanque con lote activo genera una alerta de sensor silencioso.

## Progreso
- Rama `feat/batches-and-alerts` desde `main` (`4d97052`).

- T1 completada (ruta delegada, un escritor). Dominio `Batch`/`TargetRanges`/plantillas `ale` y
  `lager` (inmutables, validación en `__post_init__`, transiciones `start`/`finish`/`edit` que
  devuelven un lote nuevo); errores `InvalidBatchError` (422), `InvalidBatchTransitionError` y
  `ActiveBatchConflictError` (409), `BatchNotFoundError` (404). Casos de uso con reloj e id
  inyectables; `merge_targets` para plantilla + overrides. Migración `0004` (`batches`, FK a `tanks`,
  CHECKs, índice único parcial `uq_batches_one_active_per_tank`). API: `GET /batch-templates`,
  `POST/GET/PATCH /batches`, `POST /batches/{id}/start|finish`; `GET /tanks` y `/tanks/{id}` con
  `active_batch` (una consulta para todos). CORS permite `PATCH`. Evidencia TDD: RED de import
  (`Batch`, `CreateBatch`, `SqlAlchemyBatchRepository`, `get_create_batch`); GREEN 375 passed;
  unitarios 320; ruff/format/mypy OK. Smoke dev: crear, iniciar, 409 por segundo activo, PATCH,
  finalizar, `active_batch` en `/tanks`, preflight `PATCH`.
- Arreglo previo (orquestador): `test_cors_origins_default_to_local_dashboard_dev_servers` fallaba
  dentro de Compose desde PR #5 porque leía el `CORS_ORIGINS` inyectado; ahora limpia la variable.
- Tamaño: ~2300 líneas (unas 1500 de dominio, aplicación y persistencia con sus tests).

- Revisión RDD de T1 (`a049ed7`, 2331 líneas, entró en una sola revisión): aprobada por el usuario,
  **aprobada** y reconocida. WARNING `R3-lost-update-save` corregido (ruta delegada): concurrencia
  optimista con `Batch.version` (+1 en cada transición o edición), `update()` con
  `WHERE id = :id AND version = :new - 1` y `ConcurrentBatchUpdateError` → 409 (field `version`);
  PATCH acepta `version` opcional (if-match). Migración `0004` editada en el lugar (nunca subida).
  RED: `ImportError ConcurrentBatchUpdateError`, `'Batch' object has no attribute 'version'`; GREEN
  385 passed (con `fermon_test` recreada por el orquestador); ruff/format/mypy OK; base dev
  re-migrada (`downgrade 0003` + `upgrade head`).

- Revisión RDD del T1 final (`050f273`, 2520 líneas): aprobada por el usuario, **aprobada** y
  reconocida. SUGGESTION `R3-empty-patch-bumps-version` corregida inline con TDD por el orquestador:
  un PATCH sin cambios no escribe ni incrementa la versión. RED `version=2 == version=1`; GREEN 386
  passed; ruff/format/mypy OK.

- T2 partida en T2a (núcleo) y T2b (API + tiempo real) por tamaño de revisión.
- T2a completada (ruta delegada, dos escritores). Dominio `Alert` (kinds `out_of_range` /
  `silent_sensor`, estados open/acknowledged/resolved, versión optimista) y reglas puras en
  `alert_rules.py`: valor igual al límite = en rango; umbrales `>=`; todo medido sobre `recorded_at`;
  `pressure_min` opcional; el alcohol nunca alerta; lecturas previas al inicio del lote se ignoran.
  Histéresis: abrir tras 5 min fuera de rango, resolver tras 2 min dentro (configurables por
  `ALERT_*`). `ReadingRepository.streak_start` (una consulta SQL sobre el índice existente, con
  ventana acotada) da el inicio de la racha actual. `IngestReading` con hook `after_created` (sus
  fallas se loguean y nunca tumban la ingesta) compuesto en `infrastructure/wiring.py` para HTTP e
  ingestor. Chequeo periódico en el ingestor (`shared/periodic.py`): barrido de alertas huérfanas +
  sensores silenciosos. Migración `0005` (`alerts`, JSONB `details`, índice único parcial
  `uq_alerts_one_unresolved`). Al finalizar un lote se resuelven sus alertas con
  `details.resolution = "batch_finished"` (hook `after_finished` + barrido de respaldo).
  Arreglo de T1 incluido: un PATCH que deja el lote igual no escribe ni sube la versión (efecto: un
  PATCH vacío sobre un lote finalizado ahora devuelve 409, coherente con "finalizado no se edita").
  Evidencia TDD: RED de import en cada capa (`AlertAction`, `CheckSilentSensors`, hook
  `after_created`, `SqlAlchemyAlertRepository`, `run_periodically`, `ResolveBatchAlerts`), `version:
  2 != 1`, `[('open', None)] == [('resolved', 'batch_finished')]`; algunos tests escritos junto a la
  implementación (declarado). GREEN 495 passed; unitarios 423; ruff/format/mypy OK. Smoke dev con
  umbrales cortos: `out_of_range` abierta (observado 19.07 contra 30–35 °C), `silent_sensor` abierta
  al detener el simulador y resuelta al reanudarlo.

- Revisión RDD de T2a (`f98c763`, 2687 líneas): aprobada por el usuario, **aprobada** y
  reconocida. Dos WARNING sobre lecturas fuera de orden (backlog del broker) corregidos dentro de
  T2a antes del push (ruta delegada):
  - R3-001: una alerta de sensor silencioso solo se resuelve con una lectura más nueva que
    `details.last_reading_at`; si esa lectura es anterior a `opened_at` (backlog) se resuelve con
    `resolved_at = opened_at` y `details.resolution = "late_data"`. Invariante de dominio:
    `acknowledged_at`/`resolved_at` >= `opened_at`.
  - R3-002: la evaluación fuera de rango se ancla en la lectura más nueva guardada del tanque y
    medición (vía `latest_per_measurement`), no en la entrante; una lectura tardía nunca resuelve
    ni abre alertas hacia atrás.
  RED: 7 failed (dominio, resolución tardía, apertura/resolución con lecturas tardías); 2 tests de
  caracterización declarados. GREEN 504 passed (verificado por el orquestador); unitarios 432;
  ruff/format/mypy OK.

- Revisión RDD del T2a final (`8db46be`, 2859 líneas): aprobada por el usuario, **aprobada** y
  reconocida. Corregido dentro de T2a (ruta delegada), última ronda acordada:
  - WARNING `R3-horizon-sparse-series`: se elimina la ventana acotada; `streak_start` se busca desde
    el inicio del lote, así las series espaciadas (p. ej. una lectura cada 15 min) abren y resuelven
    alertas correctamente. Costo documentado: escaneo proporcional a la racha actual.
  - SUGGESTION `R3-fake-streak-tie-divergence`: el fake reproduce la semántica SQL en empates entre
    clases; un test corre el mismo caso contra fake y SQL.
  RED: 4 failed (`expected 1, got 0` en fake y SQL; `datetime(12:01) == None` en el empate); 2 de
  caracterización declarados. GREEN 510 passed (verificado por el orquestador); ruff/format/mypy OK.

- T2b completada (ruta delegada, un escritor). `ListAlerts` (por defecto no resueltas, más nuevas
  primero, `limit` 1–500), `GetAlert` (404), `AcknowledgeAlert` (reconocer una ya reconocida = no-op
  200; resuelta → 409 `status`; versión vieja → 409 `version`). API `GET /alerts`, `GET /alerts/{id}`,
  `POST /alerts/{id}/acknowledge`. `GET /tanks` con `open_alerts` (un `GROUP BY` para todos).
  `RealtimeBroadcaster` generaliza el listener: una conexión, un `_Topic` por canal (lecturas y
  alertas), reconexión y health check una sola vez. Las escrituras de alertas emiten
  `pg_notify('fermon_alerts')` en SAVEPOINT con el mismo tope de 7500 bytes, solo si el insert o el
  update ocurrió. WebSocket `/ws/alerts` (`{"type":"alert","alert":...}`, 4403/1011). Evidencia TDD:
  RED de import (`manage_alerts`, `get_acknowledge_alert`, `RealtimeBroadcaster`), `TypeError` de
  constructores, 5 failed de la ruta WS, 7 failed de integración; la reescritura del broadcaster se
  escribió antes de correr sus tests (declarado). GREEN 557 passed (2 corridas del orquestador; el
  escritor vio un error no reproducible en 1 de 11 corridas); frontend 132 passed. Smoke dev con
  umbrales cortos: `open` → `acknowledged` → `resolved` (`batch_finished`) recibidos por
  `/ws/alerts`; `open_alerts` 0 → 1 → 0; reconocer una resuelta → 409.

- Revisión RDD de T2b (`4c5544b`, 1749 líneas): aprobada por el usuario, **aprobada** y reconocida.
  WARNING `R3-ack-concurrent-idempotency` corregido inline con TDD por el orquestador: sin
  `expected_version`, un conflicto de escritura se relee (hasta 3 intentos); dos "Reconocer"
  simultáneos terminan bien, y una resolución concurrente devuelve la transición inválida real
  (409 `status`) en vez de un 409 de versión opaco. Con `expected_version` el conflicto se mantiene.
  RED: 2 failed; GREEN 559 passed; ruff/format/mypy OK.
- Entrega: push y PR del backend (T1, T2a, T2b).

## Trabajo futuro
- Flaky ocasional en fixtures de integración: `TRUNCATE` sobre la hypertable choca con el job de
  refresh de los continuous aggregates (`tuple concurrently deleted`); visto una vez, no se reprodujo.

## Próximo paso
Merge del PR del backend (decisión del usuario); después T3 (UI de lotes) en una rama nueva.
