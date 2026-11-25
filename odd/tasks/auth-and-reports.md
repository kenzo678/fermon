# Feature: auth-and-reports

## Objetivo
MVP usable por la cervecería: usuarios con login, roles y permisos, y reportes deterministas por lote
(PDF + CSV, sin IA).

## Problema y por qué
Hoy cualquiera con acceso a la red puede ver y modificar todo, y no hay forma de entregar un resumen
de una fermentación. Para un MVP real hace falta controlar quién hace qué y poder documentar cada lote.

## Alcance aprobado por el usuario
### Orden
1. Usuarios + login + roles (todo lo demás se protege con esto). 2. Reportes por lote.
### Roles
- `admin`: todo + gestión de usuarios.
- `brewer`: crear/editar/iniciar/finalizar lotes, reconocer alertas, descargar reportes.
- `viewer`: solo lectura (dashboard, lotes, alertas) y descarga de reportes.
### Login
- Email + contraseña (Argon2). Sesión en cookie httpOnly (8 h), válida también para WebSockets.
- Logout y "cambiar mi contraseña". Sin registro abierto: el admin crea usuarios con contraseña
  temporal y el usuario la cambia en el primer ingreso. Primer admin por comando `create-admin`.
- Sin recuperación por email en el MVP: el admin resetea la contraseña.
### Permisos
- Toda la API y los WebSockets exigen sesión. Escrituras de lotes y reconocer alertas: admin o
  brewer. Gestión de usuarios: solo admin.
- Ingesta HTTP `POST /readings`: API key de dispositivo (no usuario). MQTT sin cambios.
- UI: login, menú según rol, acciones ocultas/deshabilitadas según rol, página "Users" para admin.
### Reportes
- PDF (plantilla HTML + WeasyPrint) y CSV desde el detalle del lote; lotes activos (parcial) y
  finalizados. Contenido: datos del lote, mín/máx/promedio por medición, % de tiempo en rango, curva
  de ABV vs. esperado, alertas y gráficos.
### Fuera del MVP
- Recuperación por email, 2FA, auditoría detallada, multi-cervecería.

## Decisiones de diseño
- Sesiones del lado del servidor: token aleatorio en la cookie, solo su hash en la base (revocables
  al hacer logout, expiran a las 8 h). Sin JWT, sin dependencias de firma extra.
- CSRF: cookie `SameSite=Lax` + header obligatorio en métodos que modifican (`X-Requested-With`).
- CORS con credenciales y orígenes explícitos (ya configurables con `CORS_ORIGINS`).

## Restricciones
- Strict TDD. Runners: backend `docker compose run --rm api uv run pytest`; frontend
  `docker compose run --rm --no-deps frontend npm test`; e2e `docker compose run --rm e2e`.
- Código, identificadores, comentarios y UI en inglés; planificación en español.
- Un commit por funcionalidad terminada, revisada y corregida; lockfiles en commit propio; push
  después de revisar y corregir.
- Rama `feat/auth-and-reports` apilada sobre `feat/batches-alerts-ui` (PR #8 sin mergear al empezar).

## Tareas
- [x] T1 — Backend de usuarios y sesiones: dominio `User`/roles, migración, Argon2, sesiones,
  `/auth/login|logout|me|password`, `/users` (admin), comando `create-admin`.
- [x] T2 — Autorización en el backend: sesión obligatoria en API y WebSockets, roles en escrituras,
  API key de dispositivo para `POST /readings`, CSRF, CORS con credenciales.
  Incluye lo que entró a main después de empezar (PRs #10–#14): perfiles de calidad
  (`/quality-profiles`, `PUT|DELETE .../specs`, `evaluate`) y análisis (`POST /batches/{id}/lab-analyses`)
  quedan como escritura de admin/brewer; sus `GET` y los catálogos, lectura con sesión.
- [x] T3 — Frontend de auth: login, sesión, rutas protegidas, UI según rol, cambio de contraseña,
  página de usuarios; e2e actualizados.
- [ ] T4 — Reportes en el backend: cálculo determinista, PDF (WeasyPrint) y CSV.
- [ ] T5 — Reportes en el frontend + e2e; PR.

## Criterios de aceptación
- Sin sesión no se ve nada; un viewer no puede modificar; un brewer no gestiona usuarios.
- Un lote finalizado descarga un PDF y un CSV con las métricas acordadas.

## Progreso
- Rama `feat/auth-and-reports` desde `origin/feat/batches-alerts-ui` (`b4f385d`).
- 2026-11-24: PR #8 y #10–#14 mergeados; rama rebasada sobre `main` (`360d2ac`). La migración de
  usuarios pasó de `0006` a `0009` (main trajo `0006`–`0008`); bases dev y de test reseteadas desde la
  `0006` vieja. Backend 782 passed; ruff/format/mypy OK.

- T1 completada (ruta delegada, un escritor). Dependencia `argon2-cffi` en commit propio `0bc7487`.
  Contexto nuevo `fermon/identity` (domain/application/infrastructure). `Role` admin/brewer/viewer con
  helpers de permisos como única fuente de verdad; `User` con email normalizado y versión optimista;
  errores con base `IdentityError` y un handler propio (formato unificado). Login con mensaje genérico
  y `verify_dummy` para no filtrar emails por tiempo. Sesiones en servidor: tabla `sessions` con
  `token_hash` como PK, 8 h (`SESSION_TTL_SECONDS`), revocadas en logout y al cambiar/resetear la
  contraseña; cookie `fermon_session` HttpOnly, SameSite=Lax, Secure configurable. Endpoints
  `/auth/login|logout|me|password` y `/users` (solo admin) con guardia del último admin
  (`LastAdminError` 409). CLI `python -m fermon.identity.create_admin` (contraseña por env o getpass,
  nunca por argv). Migración `0009` (renumerada al rebasar sobre main, que trajo `0006`–`0008`) con `identity_metadata` separada. Dependencias listas para T2:
  `get_current_user` (también para WebSocket), `require_permission`, `AdminUserDep`. Evidencia TDD: RED
  de import en cada capa y `AttributeError ... session_ttl_seconds`; GREEN 636 passed (verificado por
  el orquestador); unitarios 545; ruff/format/mypy OK; frontend 283. Smoke dev: login con cookie,
  `me`, admin crea viewer, viewer → 403 en `/users`, login inválido 401, logout → `me` 401.
  Limitación aceptada: la guardia del último admin puede competir ante dos degradaciones simultáneas.
  Restos del smoke en la base dev: `smoke-admin@example.com` y `viewer@example.com`.

- Revisión RDD de T1 (`d964fdb`, 4 lentes, riesgo alto): aprobada y reconocida; hallazgos **corregidos**
  en el árbol de trabajo (sin commit aún), Strict TDD con RED observado antes de cada GREEN:
  `must_change_password` aplicado en `get_current_user` (403, field `password`; solo `/auth/me`,
  `/auth/password` y logout lo evitan, vía `get_current_user_allow_password_change`); rate limit de
  login por email e IP (`LoginThrottle`, ventana deslizante, 429 + `Retry-After`, memoria acotada,
  settings `LOGIN_*`); Argon2 asíncrono con `asyncio.to_thread`; cambio/reseteo de contraseña +
  revocación de sesiones en una transacción (`CredentialStore`); `LastAdminError` con field
  `role`/`active` y carrera documentada; sugerencias (warning de cookie no Secure, purga de sesiones
  vencidas en login, comentarios, kwargs, `EMAIL_MAX_LENGTH=254`, assert exacto 401); más: sesión
  de usuario borrado -> 401 genérico, README sin secreto en argv, helper de overrides en tests.
  Evidencia RED: errores de import/colección (`TooManyLoginAttemptsError`, `LoginThrottle`,
  `SqlAlchemyCredentialStore`, `warn_if_cookie_not_secure`) y fallos de aserción
  (`test_temporary_password_blocks_every_route...`, `test_last_admin_cannot_be_deactivated_over_http`,
  `test_login_rejects_an_email_longer_than_the_rfc_limit`, los 4 de `test_hasher.py`).
  GREEN: backend 813 passed (base 782); ruff, format y mypy OK.

- 2026-11-24: revisión RDD de T1 rebasado (aprobada) y de sus correcciones (4 lentes, aprobada; la rama
  entera excedía el presupuesto del revisor, así que se revisaron por separado y se juntaron en un commit).
  Deuda conocida, no bloqueante (MVP con una sola instancia de API):
  - El limitador permite bloquear una cuenta ajena con 5 intentos fallidos (DoS de bloqueo); la carrera
    check-then-act deja pasar algunos intentos concurrentes; el tope de claves permite reiniciar
    contadores inundando con claves nuevas.
  - Argon2 sin límite de concurrencia (pool por defecto de `to_thread`); la purga de sesiones vencidas
    corre en el camino del login.
  - Menores: normalización de email y defaults del limitador duplicados; un fake de revocación engañoso.

- T2 completada (ruta: delegada (escritor único)). Sesión obligatoria por dependencias de router en
  `main.py` (`require_csrf_header` + `get_current_user`); la ingesta salió a `ingestion_router.py` con
  `require_device_key` (`X-Device-Key` vs `DEVICE_API_KEYS`, `hmac.compare_digest`, sin claves -> 401 y
  WARNING al arrancar). Escrituras de lotes, alertas, perfiles/specs de calidad y análisis con
  `require_permission` (helpers nuevos `can_write_quality_profiles`, `can_record_lab_analyses`);
  `evaluate` y los GET, cualquier rol. WebSockets: `get_websocket_user` y cierre `4401` (el origen, `4403`,
  se evalúa antes). CSRF: `X-Requested-With: fermon` en todo método inseguro salvo `POST /readings`
  (403, field `X-Requested-With`). CORS con credenciales; `*` rechazado en `Settings`. Prueba que recorre
  las rutas (FastAPI nuevo: hay que usar `iter_route_contexts`, `app.routes` trae routers incluidos
  perezosos) y falla si una ruta queda sin sesión/CSRF/clave. Tests: helper `tests/auth_helpers.py`
  (override del `get_current_user_allow_password_change` por cabecera `X-Test-Role`; no se desactiva la
  auth). Nada en el repo usa `POST /readings` por HTTP (simulador e ingestor van por MQTT). README,
  specs `realtime`, `reading-ingestion` y `tanks` actualizados. TDD: RED = ImportError
  (`can_record_lab_analyses`, `get_websocket_user`) y 120 fallos de la suite previa por 401/403 antes de
  adaptar los tests; las pruebas de WebSocket y de rol por router se añadieron tras la implementación
  (sin RED propio). GREEN: backend 911 passed (base 813); ruff, format y mypy OK. El frontend y sus e2e
  quedan rotos hasta T3 (esperado).

- T3 completada (ruta: delegada (escritor único)). Cliente API con `credentials: 'include'`, `X-Requested-With`
  solo en POST/PATCH (los GET no lo necesitan: evita preflights) y `apiSendEmpty` para los 204; `ApiError`
  con `retryAfterSeconds`. Módulo `features/auth` (`useSession` sobre `/auth/me`, 401 = `null`; login, logout,
  cambio de contraseña; `RequireAuth`, `RequirePermission`, `AccountMenu`) y `permissions.ts` que refleja
  `identity/domain/role.py`. `createQueryClient` revalida la sesión ante un 401 o un 403 con field `password`
  (se pregunta a `/auth/me`: un 401 por contraseña actual errónea no cierra la sesión); logout y login
  descartan toda la caché. Rutas: `/login` (vuelve a la página pedida, solo rutas internas), `/account/password`
  (un usuario con contraseña temporal queda confinado ahí, sin menú ni socket de alertas), `/users` y
  `/batches/new` con "Not allowed". UI por rol: viewer sin New batch, Start a batch, Start/Finish/Save ni
  Acknowledge (no existe UI de perfiles de calidad ni de análisis: nada que ocultar); página *Users*
  (lista, crear con contraseña temporal, rol, activar/desactivar, reset; errores 409/422). WebSocket: 4401 es
  terminal y revalida la sesión. e2e: servicio `e2e-admin` (admin sin contraseña temporal, repetible), el
  `globalSetup` entra una vez y guarda `storageState`; `frontend-e2e` sirve la API en `/api` por proxy de Vite
  porque la cookie `SameSite=Lax` no viaja entre `frontend-e2e` y `api` (sitios distintos); `auth.spec.ts`
  (login/redirección, error genérico, logout, admin crea viewer -> cambio forzado -> solo lectura).
  Evidencia TDD: RED = `apiSendEmpty is not a function` y 7 fallos de `client.test.ts` (credentials, header,
  Retry-After); imports inexistentes (`./permissions`, `./api`, `./LoginPage`, `./RequireAuth`, `UsersPage`);
  3 fallos de `AppShell` (nav/account); 5 de viewer (`controles de escritura visibles para el viewer); 4401
  (`expected 'reconnecting' to be 'unauthorized'`); 9 de `AppRoutes authentication`. `formErrors` se escribió
  con su test en el mismo paso (sin RED observado). GREEN: frontend 374 passed (base 283); lint, typecheck y
  build OK; backend 913 (sin cambios); e2e 23 passed + 1 omitido (el flujo de usuarios solo en escritorio),
  repetido una segunda vez para comprobar que `e2e-admin` es idempotente. El WebSocket de desarrollo directo
  (`localhost:5173` -> `localhost:8000`) no se probó en un navegador: se apoya en que las cookies no
  distinguen puertos y en que `localhost:5173` está en `CORS_ORIGINS` por defecto. Restos en la base dev:
  `e2e-admin@example.com`, usuarios `viewer-*@example.com` y lotes planificados "Viewer check *" en `tank-1`.

- 2026-11-24: revisión RDD de T3 (4 lentes, riesgo alto) aprobada y reconocida. Deuda no bloqueante:
  - `e2e-admin` escribe en la base dev con una contraseña pública y oculta errores (`|| echo`); usar una
    base propia para e2e antes de cualquier despliegue compartido.
  - Si `/auth/me` falla (no 401), `RequireAuth` reemplaza toda la app por un error con reintento.
  - Tras un cierre 4401 los sockets no se recuperan solos al volver a iniciar sesión sin recargar.
  - Si el logout falla en red, la UI muestra la sesión cerrada pero la cookie sigue válida.
  - El test e2e de contraseña incorrecta suma un intento al limitador (riesgo de flake si se repite
    más de 5 veces en 15 min sin reiniciar la API).
  - Menores: largo mínimo de contraseña y ruta `/account/password` duplicados; `canDownloadReports`
    oscuro; handler de 4401 duplicado en los dos hooks en vivo.

## Próximo paso
T4: reportes en el backend (cálculo determinista, PDF con WeasyPrint y CSV).
