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
- [x] T5 — `POST /readings` de ingesta + `GET /tanks/{tank_id}/readings` por rango de tiempo.
- [x] T5.1 — Seguimiento de la revisión T4.1+T5: POST honesto (`add -> bool`, `get`,
  `IngestResult`; 201 creada / 200 ya existía con el primer valor), formato 422 único
  `{"detail":[{"field","message"}]}` también para errores de Pydantic, test de health con lifespan
  real, timestamps de respuesta normalizados a UTC. Ruta: delegado (escritor).
- [x] T6 — Simulador de sensores (`simulator/`) con perfiles de fermentación e inyección de fallas.
- [x] T6.1 — Seguimiento de la revisión T6: validación de settings del simulador al cargar
  (intervalo y aceleración > 0, tasas 0..1, ruido >= 0, `disconnect_ticks` >= 1), tests unitarios de
  reconexión con backoff (cliente y espera inyectables), test de duración exacta de la ventana
  de desconexión. Ruta: delegado (escritor).
- [x] T7 — Consumidor MQTT que valida el contrato y llama a `ingest_reading`.

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

- T5 completada (ruta delegada, escritor + ajuste inline del orquestador). Adaptador HTTP:
  `ReadingIn`/`ReadingOut` (Pydantic, `extra="forbid"`, `AwareDatetime`), `POST /readings` (201,
  idempotente), `GET /tanks/{tank_id}/readings?start&end` (semiabierto), handler `DomainError` → 422
  `{"detail":[{"field","message"}]}`, lifespan con engine en `app.state`, dependencias inyectables.
  Evidencia TDD: RED `ModuleNotFoundError ... http.dependencies`, GREEN `79 passed, 13 deselected`;
  completo `92 passed`. Smoke en stack dev: POST 201 (x2 idempotente), GET 200 con 1 fila, valor 500
  → 422 con field `value`. Ajuste inline: mensaje duplicado "invalid tank_id: invalid tank_id: ..."
  (RED observado en test nuevo, GREEN con `reason` en los errores). Spot check final: 93 passed,
  ruff/format/mypy OK. Sin probar contra el stack dev: POST con fecha naive (solo unitario).

- Revisión RDD del tramo T4.1+T5 (`01b8108` → `b85daea`, 653 líneas, medio): aprobada por el
  usuario, **aprobada** y reconocida. Nuevo límite revisado: `b85daea`. Hallazgos no bloqueantes
  (seguimiento, sin autorizar todavía):
  - WARNING `R3-two-incompatible-422-shapes`: errores de dominio y de Pydantic devuelven 422 con formas distintas.
  - WARNING `R3-idempotent-post-response-may-misreport-stored-value`: un POST duplicado con otro valor responde el valor nuevo aunque la base guarda el primero.
  - SUGGESTION `R3-health-test-skips-lifespan`: el test de health no ejecuta el lifespan.
  - SUGGESTION `R3-non-utc-offset-roundtrip-unproved`: falta test de ida y vuelta con offset no UTC.

- T5.1 completada. Evidencia TDD: RED `ImportError: IngestResult` + 14 fallos (duplicado 200,
  422 unificado, add/get del repo, offsets no UTC); el test de health con lifespan es de
  caracterización (ya pasaba: el engine es lazy). GREEN `99 passed`; unitarios `82 passed,
  17 deselected`. ruff/format/mypy OK. Spot check del orquestador: 99 passed.

- Revisión RDD de T5.1 (`b85daea` → `63cacb7`, 320 líneas, medio): aprobada por el usuario,
  **aprobada** y reconocida. Nuevo límite revisado: `63cacb7`. Única sugerencia
  `R3-validation-handler-unproved-for-non-field-locs` (JSON malformado reportaba el offset como
  `field`) corregida inline: RED `assert '12' is None`, GREEN `100 passed`, ruff/format/mypy OK.

- T6 completada (ruta delegada, escritor). Proyecto `simulator/` aparte; dependencias en commit
  propio `293e177` (aiomqtt 2.5.1). Núcleo puro: `profiles` (ABV sigmoide normalizada, presión ∝
  actividad, temperatura con pico exotérmico; presets ale 19 °C/5.0 %/96 h y lager 10 °C/5.2 %/240 h),
  `faults` (ruido, pérdida, picos fuera de rango, desconexiones; semilla reproducible),
  `messages` (contrato exacto), `clock` (aceleración solo del tiempo de fermentación; `recorded_at`
  real UTC), `config` (`SIM_*`), `publisher` (aiomqtt QoS 1, reconexión con backoff 1–30 s).
  Servicio Compose con perfil `simulator`. Evidencia TDD: RED 7 errores de colección
  (`ModuleNotFoundError fermon_simulator.config`), GREEN `53 passed` (incl. integración con
  mosquitto); un fallo intermedio por contaminación de `SIM_*` del entorno, corregido en el test.
  ruff/format/mypy OK; backend sin cambios (83 unitarios OK). Smoke: `mosquitto_sub` recibió los
  6 mensajes esperados (2 tanques × 3 mediciones). Spot check del orquestador: 53 passed.
  Nota: `2c0a372` (fix JSON malformado) queda fuera de los tramos revisados, cubierto por TDD.

- Revisión RDD de T6 (`293e177` → `8ae791c`, 887 líneas, medio): aprobada por el usuario,
  **aprobada** y reconocida. Nuevo límite revisado: `8ae791c`. Hallazgos no bloqueantes
  (seguimiento, sin autorizar todavía):
  - WARNING `R3-tick-interval-unvalidated`: `tick_interval_seconds` acepta 0 o negativos (inunda el broker).
  - WARNING `R3-reconnect-backoff-unproved`: no hay test del camino de reconexión con backoff.
  - SUGGESTION `R3-disconnect-window-length-unproved`: no se prueba la duración exacta de la ventana de desconexión.

- T6.1 completada. Evidencia TDD: RED 16 failed (12 de config aceptaban valores inválidos, 4 de
  publisher con `TypeError` por `client_factory`); el test de la ventana de desconexión es de
  caracterización (sin off-by-one). GREEN `71 passed` (con broker); unitarios `70 passed`.
  ruff/format/mypy OK. Spot check del orquestador: 71 passed.

- Revisión RDD de T6.1 (`8ae791c` → `947aaea`, 198 líneas, medio): aprobada por el usuario,
  **aprobada** y reconocida. Nuevo límite revisado: `947aaea`. Corregido inline (solo tests):
  WARNING `R3-fake-wait-never-yields` (la espera falsa ahora cede el loop) y SUGGESTION
  `R3-reconnect-tests-depend-on-ambient-env` (tasas de falla fijadas en 0). Verificado con
  `SIM_DROPOUT_RATE=1.0 SIM_DISCONNECT_RATE=1.0` en el entorno: 5 passed; suite `71 passed`. No se
  observó RED previo con ese entorno hostil (no se corrió antes del arreglo).
  Pendiente sin autorizar: SUGGESTION `R3-disconnect-test-mutates-frozen-config` (el test usa
  `object.__setattr__` sobre la config del inyector).

- T7 completada (ruta delegada, escritor). Dependencia en commit propio `6b32112` (aiomqtt 2.5.1).
  Adaptador `infrastructure/mqtt` (`ReadingMessage`, `parse_topic`, `handle_message`, `run_consumer`)
  y proceso `python -m fermon.ingestor`, servicio Compose `ingestor` (corre por defecto, sesión
  persistente `clean_session=False`, QoS 1, backoff 1–30 s). Mensajes inválidos se loguean y se
  descartan; errores de infraestructura se loguean y re-lanzan. Limitación documentada: auto-ack de
  aiomqtt pierde el mensaje si la base falla al procesarlo (trabajo futuro: ack manual).
  **Desvío de TDD:** el escritor implementó antes que los tests y obtuvo un RED retroactivo moviendo
  la implementación (`ImportError: stub`, 3 errores de colección); no es un RED legítimo previo.
  GREEN `129 passed`; unitarios `110 passed, 17 deselected`; simulador `70 passed`. ruff/format/mypy
  OK. Spot check del orquestador: 129 passed. Smoke de punta a punta: simulador → mosquitto →
  ingestor → TimescaleDB → `GET /tanks/tank-1/readings` devolvió 43 lecturas en ~20 s.
  Hallazgos del smoke (seguimiento, sin autorizar todavía):
  - El simulador publica alcohol levemente negativo (≈ -0.003 a -0.07) por el ruido al inicio; el
    backend lo descarta. Corresponde recortar a 0 en el simulador.
  - Los tests de integración publican en `fermon/tanks/tank-it/...`; si el `ingestor` de dev está
    corriendo, guarda esas filas en la base de desarrollo.

- Revisión RDD de T7 (`6b32112` → `cf4f1d3`, 644 líneas, medio): aprobada por el usuario,
  **aprobada** y reconocida. Nuevo límite revisado: `cf4f1d3`. Hallazgos no bloqueantes
  (seguimiento, sin autorizar todavía):
  - WARNING `R3-ingest-failure-backoff-never-escalates`: ante caída de la base el backoff se resetea al reconectar y queda en 1 s.
  - WARNING `R3-reconnect-on-ingest-failure-drops-buffered-messages`: reconectar tras un fallo descarta mensajes ya confirmados en el buffer de aiomqtt.
  - SUGGESTION `R3-ingest-failure-test-does-not-prove-escalation`.
  - SUGGESTION `R3-integration-fixture-subscribe-race`: `sleep(1)` fijo y sesiones persistentes acumuladas en el broker.
  - SUGGESTION `R3-ingestor-shares-api-venv-volume`: `api` e `ingestor` comparten el volumen del venv.

- [x] T7.1 — Seguimiento de la revisión T7 y del smoke (ruta delegada, escritor):
  reintento en el lugar ante fallo de infraestructura (sin desconectar; backoff 1→30 s por mensaje;
  al detenerse se loguea el mensaje no guardado), `mqtt_topic_prefix` configurable (tests usan
  `fermon-test`), `mqtt_clean_session` (tests usan sesión limpia con id fijo), evento `ready` en lugar de
  `sleep(1)`, volumen propio `ingestor-venv`, y el simulador recorta a 0 el ruido de presión y alcohol
  (los picos siguen fuera de rango). Evidencia TDD: RED inicial 25 fallos (Settings rechazaba campos
  nuevos, `TypeError` en `parse_topic`/`handle_message`); para el RED de comportamiento se agregaron
  primero solo los campos de Settings (desvío menor declarado): 6 failed, p. ej.
  `assert [1.0, 1.0, ...] == [1, 2, 4, 8, 16, 30, ...]`. Simulador: RED `assert -0.04 == 0.0`.
  Caracterización declarada en varios tests. GREEN: backend `139 passed`, simulador `75 passed`;
  ruff/format/mypy OK en ambos. Smoke: sin descartes de alcohol en el ingestor; GET tank-1 → 108 filas
  (incluye datos del smoke anterior). Spot check del orquestador: 139 y 75 passed.

- Revisión RDD de T7.1 (`cf4f1d3` → `1ea8756`, 480 líneas, medio): aprobada por el usuario,
  **aprobada** y reconocida. Nuevo límite revisado: `1ea8756`. Hallazgos no bloqueantes
  (seguimiento, sin autorizar todavía):
  - WARNING `R3-retry-forever-poison-message-stalls-ingestion`: un error permanente en un mensaje bloquea la ingesta para siempre.
  - WARNING `R3-readme-duplicated-sections-contradict-new-semantics`: el README duplica secciones y se contradice sobre la pérdida de mensajes.
  - SUGGESTION `R3-mqtt-topic-env-silently-ignored`: `MQTT_TOPIC` se ignora en silencio y el prefijo no se valida.
  - SUGGESTION `R3-integration-fixed-client-id-concurrent-runs`: id fijo de cliente en tests de integración.

## Próximo paso
Decidir el seguimiento de T7.1 y cerrar la feature (PR, decisión del usuario).
