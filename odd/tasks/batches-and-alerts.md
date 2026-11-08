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
- [ ] T2 — Motor de alertas: reglas fuera de rango sostenido (5 min) y sensor silencioso (10 min),
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

## Próximo paso
T2 — motor de alertas.
