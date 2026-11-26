# Feature: quality-lab-ui

## Objetivo
Cerrar el MVP: que el flujo completo de la tesis (sensor → monitoreo → alerta → análisis de laboratorio →
reporte) se pueda demostrar desde la UI, sin `curl`, antes de pasar a los sensores físicos.

## Problema y por qué
El backend de calidad (perfiles con especificaciones de dos niveles, plantilla `pale_lager`, perfil por
lote, análisis de laboratorio evaluados y guardados) existe desde los PRs #10–#14 pero no tiene
pantallas: un analista no puede usarlo. Además, los tanques no se pueden renombrar (`display_name` sin
escritura), y en la cervecería se verían como "tank-1".

## Alcance
- Renombrar tanques: `PATCH /tanks/{id}` con `display_name` (solo `admin`: es configuración de planta)
  y su UI en el detalle del tanque.
- Perfiles de calidad en la UI: listar, crear vacío o desde plantilla, ver y editar especificaciones por
  etapa y parámetro (escritura `admin`/`brewer`, lectura todos).
- Lote ↔ perfil: elegir el perfil al crear o editar un lote; verlo en el detalle.
- Análisis de laboratorio en el detalle del lote: listar por etapa con su estado (`in_spec`, `warning`,
  `out_of_spec`, `no_spec`) y registrar uno nuevo (etapa, muestreo, analista, notas, valores por
  parámetro del catálogo).
- e2e del flujo completo y PR.

### Fuera de alcance
Editar o borrar análisis, parámetros derivados por fórmula, gráficos de control por parámetro, quién
reconoció una alerta, publicación (config de producción, retención) y sensores físicos.

## Restricciones
- Strict TDD. Runners: backend `docker compose run --rm api uv run pytest`; frontend
  `docker compose run --rm --no-deps frontend npm test`; e2e `docker compose run --rm e2e`.
- Código, identificadores, comentarios y UI en inglés; planificación en español.
- Un commit por tarea terminada, revisada y corregida; cada commit se revisa por separado (la rama
  completa excede el presupuesto del revisor); push después de revisar.
- Rama `feat/quality-lab-ui` desde `main` (`67fa94b`).
- Entrega: `ask-on-risk`; se estima ~2.5k líneas en 4 commits revisados uno por uno, un solo PR (como
  los PRs anteriores).

## Tareas
- [x] T1 — Backend: `PATCH /tanks/{id}` (`display_name`, 1–64 caracteres o `null`, solo admin), con spec
  y README. Ruta: delegada (escritor único).
- [x] T2 — Frontend: página de perfiles de calidad (lista, crear vacío/desde plantilla, editar y borrar
  especificaciones), según rol. Ruta: delegada (escritor único).
- [x] T3 — Frontend: perfil en el formulario y detalle del lote; análisis de laboratorio en el detalle
  del lote (lista con estados y formulario de carga). Ruta: delegada (escritor único).
- [ ] T4 — Frontend: renombrar tanque desde el detalle (admin); e2e del flujo completo (lote con perfil
  → análisis → reporte con el análisis); docs; PR. Ruta: delegada.

## Criterios de aceptación
- Un brewer crea un perfil desde `pale_lager`, lo asigna a un lote, carga un análisis de mosto y ve
  cada valor con su estado; el PDF del lote lo incluye.
- Un viewer ve perfiles y análisis pero no puede crearlos ni editarlos.
- Un admin renombra un tanque y el nombre aparece en el dashboard y en el reporte.

## Progreso
- Rama creada desde `main` (`67fa94b`).
- T1 hecha (sin commit aún). Ruta: delegada (escritor único). TDD: RED observado (`ImportError: cannot
  import name 'can_configure_tanks'` / `'RenameTank'`), luego GREEN con `Tank.rename`, `RenameTank`,
  `TankRepository.set_display_name`, `PATCH /tanks/{id}` (`can_configure_tanks`, solo admin). Sin
  migración (la columna existe) ni `version`: última escritura gana. `ensure` solo reescribe
  `first_seen_at`, así que no pisa el nombre. Suite 1014 passed; ruff y mypy limpios.

- T2 hecha (sin commit aún). Ruta: delegada (escritor único). TDD: RED observado en cliente
  (`TS2345: '"DELETE"' is not assignable to '"POST" | "PATCH"'`, tipos de `apiSend`/`apiSendEmpty`
  ampliados a PUT/DELETE), en módulos puros y páginas (`Failed to resolve import "./format"` y
  `"./QualityProfileDetailPage"`), y en nav/rutas (`Unable to find ... link ... name "Quality"`); luego GREEN.
  Nuevo `features/quality/` (api, hooks, format, form, páginas lista y detalle, `SpecForm`, `SpecsByStage`),
  nav "Quality" y rutas lazy. Sin cambios de backend (`canWriteQualityProfiles` ya existía). Suite 419
  passed; lint, typecheck y build limpios. Supera ~400 líneas por incluir tests y UI de dos páginas.

- Revisión RDD de T1 (`413d7bb`, riesgo medio) y de T2 (`70d44bb`, riesgo medio): aprobadas y
  reconocidas. Deuda no bloqueante de T2: si falla la carga de plantillas, el formulario de perfil nuevo
  las muestra vacías sin error; sugerencias menores en el error de borrado y la validación numérica.

- T3 hecha (sin commit aún). Ruta: delegada (escritor único). TDD: RED observado en `form.test.ts` de
  lotes (`expected undefined to be ''` para `quality_profile_id`), en la página (`Unable to find a label with
  the text of: Quality profile`), y en el módulo nuevo `features/lab/` (`Failed to resolve import "./api"`,
  `"./form"`, `"./LabAnalysesSection"`) y en el detalle (`Unable to find role="heading" and name "Lab
  analyses"`); luego GREEN. Nuevo `features/lab/` (api, hooks, form puro, format, tarjeta, formulario de
  registro, sección); `Batch.quality_profile_id` en el tipo; las sugerencias salen de la lista de perfiles ya
  cargada (incluye specs). Sin cambios de backend. Suite 467 passed; lint, typecheck y build limpios. Supera
  ~400 líneas por incluir tests y dos superficies de UI.

- Revisión RDD de T3 (riesgo medio) aprobada y reconocida; la de T1+T2 juntos (2163 líneas) también.
  Deuda no bloqueante de T3: errores del servidor que no corresponden a una fila caen como mensaje
  general; si falla la lista de perfiles, el select del lote muestra solo "None".

## Próximo paso
T4.
