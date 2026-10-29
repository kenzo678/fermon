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
- [ ] T3 — Caso de uso `ingest_reading` + puerto `ReadingRepository` (TDD con repo fake).
- [ ] T4 — Adaptador SQLAlchemy/Timescale + migración Alembic con hypertable (integración).
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

## Próximo paso
T3 — Caso de uso `ingest_reading` + puerto `ReadingRepository` (TDD con repo fake).
