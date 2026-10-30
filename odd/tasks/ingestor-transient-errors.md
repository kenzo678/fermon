# Feature: ingestor-transient-errors

## Objetivo
Que el ingestor MQTT no descarte lecturas por fallas temporales de disponibilidad de la base.

## Problema y por qué
Dos pendientes de la revisión de T7.2 (`odd/tasks/backend-foundation.md`, "Trabajo futuro"):
- `sqlalchemy.exc.TimeoutError` (pool de conexiones agotado) no hereda de `DBAPIError` ni del
  `TimeoutError` builtin, así que `is_transient` lo trata como permanente y descarta el mensaje.
- Si el ingestor arranca antes de `alembic upgrade head`, cada mensaje falla con `ProgrammingError`
  (tabla inexistente), que es permanente, y se descarta todo en silencio (solo un log ERROR).

## Alcance autorizado
- `backend/src/fermon/fermentation/infrastructure/mqtt/consumer.py`, `backend/src/fermon/ingestor.py`,
  el adaptador de persistencia si hace falta, tests y README.
- Fuera de alcance: ack manual de MQTT, frontend, WebSocket.

## Restricciones
- Strict TDD, runner `docker compose run --rm api uv run pytest`.
- Entrega: un solo commit de feature terminada y corregida (preferencia del usuario); los commits
  intermedios quedan locales y se aplastan antes del push.

## Tareas
- [x] T1 — `is_transient` clasifica `sqlalchemy.exc.TimeoutError` como transitorio (con test).
- [x] T2 — El ingestor verifica al arrancar que el esquema esté migrado (tabla `readings`, revisión
  de Alembic en head) y espera con backoff, logueando, hasta que lo esté; no consume mensajes antes.
  README actualizado.
- [x] T3 — Revisión RDD del cambio completo, correcciones, squash en un commit, push y PR.

## Criterios de aceptación
- Pool agotado → el mensaje se reintenta, no se descarta.
- Ingestor arrancado sin migración → no descarta mensajes; empieza a consumir cuando la migración
  se aplica (la sesión persistente de MQTT conserva los mensajes mientras tanto).

## Progreso
- Rama `fix/ingestor-transient-errors` creada desde `main` (`94408b0`).

- T1 y T2 completadas (ruta delegada, un escritor). `is_transient` incluye
  `sqlalchemy.exc.TimeoutError`. Nuevo `infrastructure/schema.py` (`alembic_config`,
  `schema_is_ready`, `wait_for_schema` con backoff 1→30 s) y `shared/waiting.py` (`sleep_or_stop`
  compartido). El ingestor espera el esquema antes de consumir. Evidencia TDD: RED T1
  `assert False is True ... is_transient(TimeoutError('QueuePool limit reached'))`; RED T2
  `ModuleNotFoundError ... infrastructure.schema` (RED de import); 2 tests cercanos a
  caracterización (ya listo, ya detenido). GREEN `171 passed`; unitarios `151 passed`.
  ruff/format/mypy OK. Smoke con base descartable `fermon_smoke_test`: WARNING con backoff 4 s → 8 s,
  `alembic upgrade head`, INFO "database schema is ready" y suscripción. Spot check: 171 passed.

- Revisión RDD (`94408b0` → `ddcb7fb`, 293 líneas, medio): aprobada por el usuario, **aprobada** y
  reconocida. Hallazgos corregidos dentro de la misma feature antes del squash (ruta delegada):
  - WARNING `R3-ingestor-gating-untested`: `fermon.ingestor.run(...)` con colaboradores inyectables y
    `main() -> int`; tests de que el consumidor no arranca antes del esquema listo y del dispose.
  - WARNING `R3-schema-runtime-layout-dependency`: `Settings.alembic_ini_path` (`ALEMBIC_INI_PATH`);
    `CommandError` → `SchemaCheckError` sin reintento, el ingestor loguea ERROR y sale con código 1.
  - SUGGESTION `R3-revision-ahead-misleading`: `SchemaState` READY / BEHIND (espera) /
    UNKNOWN_REVISION (falla rápido).
  - SUGGESTION `R3-connectivity-test-weak-assertions`: WARNING "database unavailable" por fallo,
    parametrizado (OperationalError, SQLAlchemyError, OSError, TimeoutError).
  Evidencia TDD: RED de import `ImportError: cannot import name 'SchemaCheckError'` (cubre los 4
  ítems a la vez); el test de `alembic_ini_path` y la integración READY/BEHIND no tuvieron RED propio.
  GREEN `187 passed`; unitarios `167 passed`. ruff/format/mypy OK. Spot check del orquestador:
  187 passed y arranque real del ingestor en el stack dev ("schema is ready" → suscripto).
  Sin nueva ronda de revisión (acotado).
- Entrega: squash en un único commit sobre `main`, push y PR.

## Próximo paso
Merge del PR (decisión del usuario).
