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
- [x] T2 — Vista general de tanques: `GET /tanks` con TanStack Query, tarjetas responsive con la
  última lectura por medición, estados de carga, error y vacío.
- [x] T3 — Detalle de tanque: ruta `/tanks/:id`, gráficos ECharts de temperatura, presión y alcohol
  desde el endpoint agregado, selector de rango y bucket (1m/1h), 404 de tanque.
- [x] T4 — En vivo: hook WebSocket con reconexión y relleno vía REST; la vista general y el detalle
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

- T2 completada (ruta delegada, un escritor). Dependencias en commit propio `7d45e06`
  (`@tanstack/react-query` 5.106.0, `react-router` 8.5.1). Rutas `/`, `/tanks/:tankId` (placeholder
  hasta T3) y no encontrada. `shouldRetry`: nunca reintenta `ApiError` 4xx; red y 5xx hasta 2
  reintentos. `features/tanks`: `fetchTanks`/`tankKeys`, `useTanksQuery`, contenedor
  `TanksOverviewPage`, presentacionales `TankCard`, `TankGrid` (1/2/3–4 columnas), `EmptyState`,
  `ErrorState` (reintento), `LoadingState`. Unidades fijas por medición (°C, bar, % ABV), "—" sin
  lectura, horas absolutas en `<time>`. Accesibilidad: `ul`/`li`, `article`, `h2`/`h3`,
  `role=status`/`alert`. Evidencia TDD: RED 5 archivos con "Failed to resolve import" (RED de
  import); GREEN 46/46; lint, typecheck y build limpios. Smoke: SPA en 5173, `/tanks` con tank-1 y
  tank-2. Spot check del orquestador: 46 passed. Tamaño ~624 líneas (mitad tests).

- Revisión RDD de T2 (`b660f10`, 635 líneas): aprobada por el usuario, **aprobada** y reconocida.
  Corregido inline con TDD por el orquestador (amend):
  - WARNING `R3-background-refetch-error-hides-data`: los datos en cache ganan sobre un refetch
    fallido; se mantiene la grilla y se muestra un aviso no bloqueante "Couldn't refresh".
  - WARNING `R3-invalid-date-throws`: `formatDateTime` devuelve "—" ante una fecha malformada.
  - SUGGESTION `R3-retry-no-feedback`: no aplica en TanStack Query v5 (un error sin datos vuelve a
    `pending` al reintentar y se ve el estado de carga); se fijó con un test de caracterización.
  - SUGGESTION `R3-readme-nginx-fallback-unproved`: ya cubierto, `nginx.conf` tiene
    `try_files $uri /index.html` desde T1.
  RED: 3 failed; GREEN 50/50; lint, typecheck y build limpios.

- Revisión RDD de la rama T1+T2 desde `main` (6208 líneas, pedida por el hook): aprobada por el
  usuario, **aprobada** y reconocida. Hallazgos sobre código de T2 corregidos dentro del commit de T3
  (T2 ya estaba subido; se evita el force push):
  - WARNING `R3-newest-timestamp-malformed-sticks`: `newestTimestamp` ignora fechas malformadas en
    cualquier posición. RED `expected 'garbage' to be '2026-01-01T13:00:00Z'`.
  - SUGGESTION `R3-no-retry-proved-by-sleep`: tests puros y deterministas de `shouldRetry` (400/404/
    422/499 nunca; 0/500/503 y no-API hasta 2). De caracterización (la lógica ya era correcta).
- T3 completada (ruta delegada, un escritor + ajustes del orquestador). Dependencia en commit propio
  `7f40f6f` (echarts 6.1.0). `features/readings`: `range.ts` (`rangeToQuery`, `parseRange`; 1h/6h en
  1m, 24h/7d en 1h, máx. 360 puntos), `?range=` en la URL (24h por defecto), `RangeSelector`
  (radiogroup), `TimeSeriesChart` (ECharts por módulos, `ResizeObserver`, dispose),
  `MeasurementChart` (promedio + banda mín–máx, "No data in this range"),
  `useAggregatedReadingsQuery` ("now" calculado por request dentro de `queryFn`). `TankDetailPage`
  con encabezado, 404 "Tank not found" y errores con reintento. Ajuste del orquestador: la ruta de
  detalle se carga de forma diferida (`React.lazy`), así ECharts no entra en el bundle principal:
  principal 298 kB (94 kB gzip), detalle 552 kB (186 kB gzip; queda el aviso de chunk > 500 kB).
  Evidencia TDD: RED de import ("Failed to resolve import ./range", "./MeasurementChart", etc.);
  GREEN 85/85; lint, typecheck y build limpios. Smoke: el endpoint agregado devuelve puntos 1m para
  tank-1. Sin probar: renderizado real del canvas (jsdom no tiene canvas; queda para el e2e de T5).

- Revisión RDD de T3 (`d0fc347`, 874 líneas): aprobada por el usuario, **aprobada** y reconocida.
  Corregido inline con TDD por el orquestador (amend):
  - WARNING `R3-lazy-detail-no-error-boundary`: `RouteErrorBoundary` alrededor de la ruta diferida;
    si el chunk no carga se muestra "This page failed to load" con "Reload" y "Back to tanks".
  - SUGGESTION `R3-setoption-notmerge-resets-zoom`: `setOption(option, { replaceMerge: ["series"] })`
    conserva el zoom del usuario en los refetch (importante para T4).
  RED: 2 aserciones del gráfico + módulo del boundary inexistente; GREEN 87/87; lint, typecheck y
  build limpios.

- Revisión RDD de la rama T1+T2+T3 desde `main` (7144 líneas, pedida por el hook): aprobada por el
  usuario, **aprobada** y reconocida. Hallazgos sobre código de T3 corregidos dentro del commit de T4
  (T3 ya estaba subido) por el orquestador con TDD:
  - WARNING `R3-band-stack-negative-min`: la banda usa `stackStrategy: "all"` para mínimos negativos.
  - SUGGESTION `R3-error-boundary-sticky-across-tanks`: `RouteBoundary` reinicia el boundary al
    cambiar de URL (con `key` por `pathname`).
  - SUGGESTION `R3-index-html-cache-stale-chunks`: nginx sirve el shell con `Cache-Control: no-cache`
    (verificado con `curl -I` contra la imagen de producción en `/`, `/tanks/tank-1` e `/index.html`).
  RED: 2 failed (banda y reinicio del boundary); GREEN 115/115.
- T4 completada (ruta delegada, un escritor). `shared/realtime`: `wsUrlFor` (deriva ws/wss de la base
  de la API con las reglas de `buildUrl`), `createReconnectingSocket` (backoff 1→30 s con reinicio al
  abrir, JSON malformado descartado, 4403/4404 terminales, 1011 y cierres anormales reconectan),
  `RealtimeProvider` como inyección del `socketFactory` (los tests usan `FakeSocket`).
  `useLiveReadings`: un socket por tanque; actualiza la cache de la lista y del detalle solo con
  lecturas estrictamente más nuevas (sin crear entradas); refresco de los agregados limitado a uno
  cada 15 s por tanque; en cada reapertura invalida lista, detalle y agregados (relleno vía REST).
  `ConnectionIndicator` Live / Reconnecting… / Offline en ambas páginas. Limitación: si cambia el
  conjunto de tanques se recrean todos los sockets. Evidencia TDD: RED de import (realtime, hook) y
  2 tests de páginas sin cablear; GREEN 114/114 (115 con las correcciones). lint, typecheck y build
  limpios. Smoke: 3 mensajes en vivo de tank-1 recibidos por WebSocket desde el contenedor.

- Revisión RDD de T4 (`569fde5`, 889 líneas) y de la rama desde `main` (8005 líneas, pedida por el
  hook): ambas aprobadas por el usuario, **aprobadas** y reconocidas. Corregido dentro de T4 antes
  del push:
  - (ruta delegada) WARNING backfill al reconectar sin probar → MSW confirma lista, detalle y
    agregados (caracterización: las claves ya eran correctas).
  - (ruta delegada) `aggregateStatus` exportado: ignora sockets terminales (4403/4404); un tanque
    eliminado ya no pone "Offline" la vista general. RED: 10 casos `aggregateStatus is not a function`.
  - (ruta delegada) Reconexiones en ráfaga: invalidación de la lista con debounce de 250 ms y
    `cancelRefetch: false`; el refresco de agregados al reconectar pasa por el mismo throttle de 15 s.
    RED: `got 3` (refetch de lista) y `got 2` (agregados).
  - (ruta delegada) Factory que lanza al crear el socket → reconecta con backoff (caracterización).
  - (orquestador) SUGGESTION `R3-consumer-errors-logged-as-malformed`: parseo y consumo separados;
    un error del consumidor se reporta como "Realtime message handler failed". RED observado.
  - (orquestador) Regresión detectada: el overview importaba el barrel de `readings` y metía ECharts
    en el bundle principal (853 kB). Imports directos + regla ESLint `no-restricted-imports` que lo
    impide (probada con un archivo de prueba que la dispara). Bundle principal 303 kB (96 kB gzip).
  GREEN 132/132; lint, typecheck y build limpios.

## Próximo paso
T5 — e2e con Playwright y PR.
