# OpenSpec de Fermon

Línea base (baseline) de especificaciones de lo que **ya está construido y fusionado** (hasta `main` en
`21824f4`). Describe comportamiento verificado contra el código; no propone cambios.

## Contenido

- `config.yaml`: contexto del proyecto y reglas (TDD estricto, runners de Docker, convenciones de commits).
- `specs/<dominio>/spec.md`: fuente de verdad por capacidad:
  `reading-ingestion`, `reading-storage-and-query`, `tanks`, `batches`, `alerts`, `realtime`,
  `sensor-simulator`, `dashboard-frontend`.
- `changes/`: cambios activos (uno por carpeta). `changes/archive/`: cambios cerrados (`YYYY-MM-DD-nombre`).
  Hoy ambas están vacías.

## Relación con `odd/tasks/`

- `odd/tasks/*.md` es el **historial**: decisiones, evidencia TDD, revisiones y trabajo futuro por feature.
- `openspec/specs/` es el **estado actual** destilado de ese historial (qué hace el sistema hoy).
- Un cambio nuevo se escribe como delta en `openspec/changes/<nombre>/` y, al archivarse, se fusiona en
  `specs/`. Los documentos de planificación van en español; el código y los textos de UI en inglés.

## Continuar en otra PC

```sh
git pull                    # trae openspec/ y odd/
engram sync --import        # importa la memoria (Engram) compartida
```

Luego retomar con `mem_context` / `mem_search` del proyecto y leer `odd/tasks/batches-and-alerts.md`.

## Qué sigue

1. Frontend de `batches-and-alerts` (rama nueva desde `main`):
   - **T3** UI de lotes: formulario con plantillas, estados, lote activo en tarjeta y detalle, bandas de
     rango objetivo en los gráficos.
   - **T4** UI de alertas: contador, página con filtros, "Reconocer", indicador en la tarjeta, aviso en
     vivo (`/ws/alerts`).
   - **T5** e2e de lotes y alertas con el simulador forzando una desviación; PR del frontend.
2. Después, el **generador de reportes determinista** por lote (PDF + CSV, sin IA), apoyado en
   `started_at`, `finished_at`, `targets`, lecturas agregadas y alertas del lote.
