# Feature: dashboard-overview

## Objetivo
Primera versión del frontend web responsive de Fermon: vista general de tanques con su estado
actual, detalle de tanque con gráficos de series agregadas y actualizaciones en vivo.

## Problema y por qué
El backend ya expone `GET /tanks`, `GET /tanks/{id}`, `GET /tanks/{id}/readings/aggregated` y
`/ws/tanks/{id}`, pero no hay interfaz. La tesis requiere una aplicación usable en escritorio,
laptop, tablet y celular.

## Stack decidido (aprobado por el usuario)
- React + TypeScript + Vite; npm como gestor de paquetes.
- TanStack Query para REST; hook propio sobre WebSocket nativo (reconexión con backoff y relleno
  vía REST al reconectar, porque el WebSocket del backend es best-effort).
- Apache ECharts para series temporales; Tailwind CSS (mobile-first); React Router.
- Screaming architecture por features (`src/features/tanks`, `src/features/readings`, `src/shared`)
  + patrón container/presentational (presentacionales puros y testeables).
- Tests: Vitest + Testing Library + MSW (mocks de la API); Playwright para e2e.
- `frontend/` dockerizado: Vite dev server en desarrollo, nginx en producción; servicio en el mismo
  `docker-compose.yml`.

## Alcance autorizado
`frontend/`, `docker-compose.yml`, README. Fuera de alcance: autenticación, lotes, alertas,
cambios en el backend (salvo lo estrictamente necesario, consultando antes).

## Restricciones
- Strict TDD; runner: `docker compose run --rm frontend npm test` (se fija en T1).
- Código, identificadores, comentarios y textos de UI en inglés; planificación en español.
- Entrega: un commit por funcionalidad terminada, revisada y corregida; push recién después de la
  revisión y sus correcciones. El lockfile (`package-lock.json`) va en su propio commit.

## Tareas
- [x] T1 — Scaffold de `frontend/`: Vite + React + TS, Tailwind, ESLint, Vitest + Testing Library +
  MSW, cliente de API tipado, Dockerfile multi-stage (dev / nginx), servicio en Compose, layout
  responsive base con un test.
- [ ] T2 — Vista general de tanques: `GET /tanks` con TanStack Query, tarjetas responsive con la
  última lectura por medición, estados de carga, error y vacío.
- [ ] T3 — Detalle de tanque: ruta `/tanks/:id`, gráficos ECharts de temperatura, presión y alcohol
  desde el endpoint agregado, selector de rango y bucket (1m/1h), 404 de tanque.
- [ ] T4 — En vivo: hook WebSocket con reconexión y relleno vía REST; la vista general y el detalle
  se actualizan solos; indicador de conexión.
- [ ] T5 — e2e con Playwright contra el stack con simulador; PR.

## Criterios de aceptación
- Con el simulador corriendo, la vista general muestra tank-1 y tank-2 y se actualiza sola.
- El detalle muestra los tres gráficos y se adapta a celular, tablet y escritorio.

## Progreso
- Rama `feat/dashboard-overview` desde `main` (`063e20f`).

- T1 completada (ruta delegada, un escritor). Manifiesto y lockfile en commit propio `f4dd901`.
  node:22-alpine, nginx:1-alpine; react 19.3, vite 8.3, typescript 6.0, tailwindcss 4.3, vitest 5.1,
  msw 3.0 (desvío: npm resolvió MSW 3 en lugar de 2; `onUnhandledRequest` pasó a `onUnhandledFrame`).
  Prettier omitido. Cliente `apiGet<T>` con `ApiError(status, detail)` (status 0 = falla de red),
  tipos espejo del backend, `AppShell` presentacional. Dockerfile base/dev/build/prod (nginx con
  fallback SPA); servicio `frontend` en Compose (5173, volumen `frontend-node-modules`).
  Evidencia TDD: RED "Failed to resolve import './AppShell'" / './client' (2 archivos fallidos);
  GREEN 8/8. lint y typecheck limpios; build OK; imagen prod OK; dev server responde en 5173;
  backend sin cambios (249 unitarios). Spot check del orquestador: 8 passed.
  Runner: `docker compose run --rm --no-deps frontend npm test`.

- Revisión RDD de T1 (`16b7d0b`, 486 líneas) y de la rama desde `main` (5247 líneas con lockfile,
  pedida por el hook): ambas aprobadas por el usuario, **aprobadas** y reconocidas; hallazgos
  coincidentes, corregidos dentro de T1 antes del push (ruta delegada):
  - WARNING base URL de tests acoplada al entorno → `test.env.VITE_API_URL` fijo y handlers desde `API_URL`.
  - WARNING cuerpo 2xx no JSON (HTML, vacío, 204) → `ApiError(status, [], "Invalid JSON response")`.
  - WARNING prefijo de ruta perdido / base vacía → `buildUrl` une base y ruta sin perder el prefijo;
    base vacía o relativa = mismo origen; URL inválida → `ApiError(0, "Invalid API URL configuration")`.
  - SUGGESTION/WARNING abort → si `signal.aborted`, se relanza `signal.reason` (el chequeo previo con
    `instanceof DOMException` nunca coincidía en jsdom/undici).
  RED: 10 failed (p. ej. `SyntaxError ... to be an instance of ApiError`, `buildUrl is not a function`);
  GREEN 18/18; lint, typecheck y build limpios. Spot check del orquestador: 18 passed.

- Revisión RDD del T1 final (`54936e4`, 604 líneas): aprobada por el usuario, **aprobada** y
  reconocida. Corregido inline con TDD por el orquestador (amend, sin otra ronda):
  - WARNING `R3-abort-during-body-read`: un abort durante la lectura del cuerpo (éxito o error) se
    propaga con su motivo, nunca como `ApiError` (`rethrowIfAborted` en las tres etapas).
  - WARNING `R3-stale-node-modules-volume`: README indica recrear el volumen (`up -V` o `volume rm`).
  - SUGGESTION `R3-schemeless-base-relative`: una base sin esquema que no empieza con `/`
    (p. ej. `localhost:8000`) es configuración inválida → `ApiError(0)`.
  RED: 3 failed (los dos aborts durante el cuerpo y la base sin esquema); GREEN 21/21; lint,
  typecheck y build limpios.

## Próximo paso
T2 — vista general de tanques.
