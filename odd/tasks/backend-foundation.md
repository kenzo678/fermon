# Feature: backend-foundation

## Objetivo
Construir la base del backend de Fermon: ingesta, validación y almacenamiento de lecturas de
temperatura, presión y alcohol de los tanques de fermentación, alimentada inicialmente por un
simulador de sensores.

## Problema y por qué
La tesis necesita un backend que reciba datos de tres fuentes sucesivas (sensores simulados,
sensores caseros ESP32 y sensores industriales reales) sin cambiar el dominio. Un contrato de
mensaje único y una arquitectura hexagonal hacen intercambiables esas fuentes.

## Alcance autorizado
- Monorepo: `docker-compose.yml` en la raíz, `backend/`, `simulator/`.
- Todo dockerizado (tests y herramientas incluidos).
- Fuera de alcance: frontend, autenticación, alertas, WebSocket (features posteriores).

## Restricciones
- Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2.0 async + asyncpg, Alembic, aiomqtt.
- PostgreSQL + TimescaleDB, Mosquitto.
- Herramientas: uv, ruff, mypy, pytest, pytest-asyncio, httpx.
- Código, identificadores y comentarios en inglés; documentación de planificación en español.
- Conventional Commits, un commit por tarea, en la rama `feat/backend-foundation`.

## Contrato de mensaje
Tópico MQTT `fermon/tanks/{tank_id}/readings`, payload JSON:
`{"sensor_id": str, "measurement": "temperature|pressure|alcohol", "value": float, "unit": str, "recorded_at": ISO-8601}`

## TDD
- Modo: Strict TDD activado (fuente: configuración de sesión del orquestador).
- Runner: `docker compose run --rm api uv run pytest` (se establece en T1).

## Estrategia de entrega
- `ask-on-risk` (por defecto). Pronóstico: ~1200 líneas en total, supera las 400, así que se
  preguntará la estrategia de encadenamiento antes del commit que cruce el presupuesto.

## Tareas
- [x] T1 — Scaffold del monorepo: `backend/` (uv, ruff, mypy, pytest), `backend/Dockerfile`
  multi-stage, `docker-compose.yml` (api, timescaledb, mosquitto), endpoint `GET /health` con test.
  Ruta: delegado (escritor) — dispara el trigger de 2+ archivos no triviales.
- [x] T2 — Dominio: `Reading` y `MeasurementType` con validación por tipo de medición (TDD).
- [x] T3 — Caso de uso `ingest_reading` + puerto `ReadingRepository` (TDD con repo fake).
- [x] T3.1 — Seguimiento de la revisión T2+T3: normalización compartida de ids (`normalize_id`,
  `InvalidIdentifierError`), `ListReadings` limpia/valida `tank_id`, errores de dominio para tipos
  inválidos, tests del guard de `measurement` y de tzinfo sin offset. Ruta: delegado (escritor).
- [x] T4 — Adaptador SQLAlchemy/Timescale + migración Alembic con hypertable (integración).
- [x] T4.1 — Seguimiento de la revisión T4: test first-write-wins, rutas de Alembic absolutas,
  guard `_test` para `TEST_DATABASE_URL`, tests de drift y de ciclo downgrade/upgrade,
  `validate_time_range` de dominio compartido por caso de uso y adaptador. Ruta: delegado.
- [ ] T5 — `POST /readings` de ingesta + `GET /tanks/{tank_id}/readings` por rango de tiempo.
- [ ] T6 — Simulador de sensores (`simulator/`) con perfiles de fermentación e inyección de fallas.
- [ ] T7 — Consumidor MQTT que valida el contrato y llama a `ingest_reading`.

## Criterios de aceptación
- Tests en verde dentro de Docker en cada tarea (RED → GREEN → REFACTOR observado).
- `docker compose up` con el simulador activo: las lecturas se almacenan y el GET las devuelve.

## Progreso
- Commit raíz `dc58aa2` en `main` (vacío, para que la rama tenga base). Rama creada.
- T1 completada (ruta delegada). Evidencia TDD: RED `assert 404 == 200`, GREEN `1 passed`.
  Checks: build OK, pytest 1 passed, ruff check/format OK, mypy sin errores, `curl /health`
  → `{"status":"ok"}`, timescaledb healthy. Spot check del orquestador: pytest 1 passed.
  Notas: sin BuildKit en el host, por eso no se usa `--mount=type=cache`; el `.venv` vive en
  un volumen nombrado `api-venv` (tras cambiar dependencias: `docker compose build api` y
  `docker volume rm fermon_api-venv`). ~200 líneas de autor (sin lock).
- Commits T1: `b86a01f` (scaffold) + commit siguiente con `backend/uv.lock` (generado).
  El commit original con el lock superó el presupuesto de contexto del revisor
  (`lens_context_budget_exceeded`), por eso se partió. Revisión RDD de `b86a01f`: riesgo medio,
  aprobada por el usuario; un BLOCKER (`R3-missing-uv-lock`) causado por la partición misma,
  que se resuelve con el commit del lock (no entraba en la corrección acotada de 135 líneas).
  Revisión descartada con autorización del usuario (`operator_disposition`, actor kenzo678).

- T2 completada (ruta delegada, escritor). Dominio puro sin dependencias de framework.
  Unidades canónicas: celsius, bar, percent_abv. Límites físicos inclusivos: -20..100,
  0..10, 0..20 (en `measurement.py`). Evidencia TDD: RED `ImportError: cannot import name
  'DomainError'`, GREEN `24 passed`. ruff/format/mypy OK. Spot check del orquestador: 24 passed.

- T2 commit `f87aba5`; RDD assess (base `8bf864e`): medio, `under_budget` (210 líneas), pendiente en el tramo.
- T3 completada (ruta delegada, escritor). `IngestReading` + `IngestReadingCommand`,
  `ListReadings` (rango semiabierto [start, end), orden ascendente), puerto `ReadingRepository`
  (Protocol), `InvalidTimeRangeError`. Fake `InMemoryReadingRepository` en tests. Evidencia TDD:
  RED `ImportError: cannot import name 'ListReadings'`, GREEN `32 passed`. ruff/format/mypy OK.
  Spot check del orquestador: 32 passed.
- Revisión RDD del tramo T2+T3 (base `8bf864e` → `0314fc9`, 434 líneas, riesgo medio): aprobada
  por el usuario, **aprobada** y reconocida (autoridad quemada). Nuevo límite revisado: `0314fc9`.
  Hallazgos no bloqueantes (seguimiento, sin autorizar todavía):
  - WARNING `R3-list-tank-id-asymmetry`: `ListReadings` no normaliza ni valida `tank_id` como el dominio.
  - SUGGESTION `R3-non-domain-exceptions-on-bad-types`: tipos inválidos escapan como TypeError/AttributeError.
  - SUGGESTION `R3-measurement-type-guard-untested`: falta test del guard `isinstance` de `measurement`.
  - SUGGESTION `R3-tzinfo-none-offset-untested`: falta test de tzinfo con `utcoffset()` None.
- T3.1 completada. Evidencia TDD: RED 9 failed (`test_wrong_types_raise_domain_error`) +
  `ImportError: InvalidIdentifierError` en tests de ListReadings; los tests de los ítems 3 y 4 son
  de caracterización (pasaron de entrada, el comportamiento ya existía). GREEN `49 passed`.
  ruff/format/mypy OK. Spot check del orquestador: 49 passed. Los 4 hallazgos quedan resueltos.
- Política: push a `origin` después de cada commit de tarea (pedido del usuario).

- Revisión RDD de T3.1 (`0314fc9` → `ef61304`, 159 líneas, medio): aprobada por el usuario,
  **aprobada** y reconocida. Sugerencia no bloqueante aceptada como está:
  `R3-value-type-guard-narrows-numeric-inputs` (Decimal/Fraction/numpy se rechazan; los
  adaptadores envían float).
- T4 completada (ruta delegada, escritor). Dependencias en commit propio `34a0aa6`
  (sqlalchemy 2.1.6, asyncpg, alembic; `uv.lock` aislado por el presupuesto del revisor).
  Tabla `readings` (Core), unique `uq_readings_identity` (tank, sensor, medición, recorded_at),
  índice (tank_id, recorded_at DESC), ingesta idempotente `ON CONFLICT DO NOTHING`,
  hypertable con `create_hypertable('readings', by_range('recorded_at'))` (TimescaleDB 2.31.0).
  Alembic async. Tests de integración (`-m integration`) sobre la base `fermon_test`.
  Evidencia TDD: RED `ModuleNotFoundError ... persistence`, GREEN `54 passed`; solo unitarios
  `49 passed, 5 deselected`; `alembic upgrade head` OK en la base dev. ruff/format/mypy OK.
  Spot check del orquestador: 54 passed. Sin probar: downgrade de Alembic.
- Runner completo: `docker compose run --rm api uv run pytest`; unitarios sin base:
  `docker compose run --rm --no-deps api uv run pytest -m "not integration"`.

- Revisión RDD de T4 (`34a0aa6` → `01b8108`, 431 líneas, medio): aprobada por el usuario,
  **aprobada** y reconocida. Nuevo límite revisado: `01b8108`. Sugerencias no bloqueantes
  (seguimiento, sin autorizar todavía):
  - `R3-duplicate-test-does-not-prove-first-write-wins`: el test de duplicado no verifica que se conserve el primer valor.
  - `R3-alembic-config-cwd-dependent`: el conftest carga Alembic con rutas relativas al cwd.
  - `R3-truncate-honors-arbitrary-test-url`: `TEST_DATABASE_URL` sin guard; podría truncar la base dev.
  - `R3-migration-metadata-drift-and-downgrade-unproved`: sin test de drift migración↔tabla ni de downgrade.
  - `R3-list-by-tank-range-bounds-unvalidated`: el adaptador no valida datetimes naive/rango invertido.

- T4.1 completada. Evidencia TDD: RED `ModuleNotFoundError` (módulos nuevos) y 4 fallos
  "DID NOT RAISE InvalidTimeRangeError" en el adaptador; first-write-wins, guard y migraciones
  son tests de caracterización. GREEN `72 passed` (también desde cwd `/app/tests`); unitarios
  `61 passed, 11 deselected`. ruff/format/mypy OK. Spot check del orquestador: 72 passed.
  Nota: el test de drift filtra solo `readings_recorded_at_idx`, índice que crea
  `create_hypertable()` por su cuenta (alternativa futura: `create_default_indexes => false`).

## Próximo paso
T5 — `POST /readings` + `GET /tanks/{tank_id}/readings` por rango de tiempo.
