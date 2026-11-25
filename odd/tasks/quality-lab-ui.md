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
- [ ] T2 — Frontend: página de perfiles de calidad (lista, crear vacío/desde plantilla, editar y borrar
  especificaciones), según rol. Ruta: delegada.
- [ ] T3 — Frontend: perfil en el formulario y detalle del lote; análisis de laboratorio en el detalle
  del lote (lista con estados y formulario de carga). Ruta: delegada.
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

## Próximo paso
T2.
