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
- [ ] T2 — Series agregadas: continuous aggregates 1m/1h + `GET /tanks/{tank_id}/readings/aggregated`.
- [ ] T3 — Tiempo real: NOTIFY desde el ingestor, LISTEN en la API, WebSocket `/ws/tanks/{tank_id}`.
- [ ] T4 — PR.

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

## Próximo paso
T2 — series agregadas.
