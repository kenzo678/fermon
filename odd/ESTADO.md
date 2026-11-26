# Estado del proyecto Fermon

Última actualización: 2026-11-25 (`main` en `be78767`, 18 PRs fusionados).

## Resumen
La parte de software del MVP está **completa y demostrable de punta a punta desde la UI**: sensor
(simulado) → monitoreo en vivo → alerta → análisis de laboratorio → reporte PDF/CSV. Falta el hardware
(sensores caseros y luego los reales) y la puesta en producción.

## Qué está construido

| Área | Contenido | Doc de la feature |
| --- | --- | --- |
| Ingesta | MQTT (QoS 1) e HTTP con API key de dispositivo; validación de unidades y rangos físicos; ingestor tolerante a fallos transitorios | `backend-foundation.md`, `ingestor-transient-errors.md` |
| Almacenamiento | TimescaleDB: hypertable `readings`, agregados continuos `readings_1m` y `readings_1h` | `backend-foundation.md`, `dashboard-ready-backend.md` |
| Dashboard | Tanques en vivo (WebSocket), detalle con gráficos ECharts y bandas objetivo; responsive | `dashboard-overview.md` |
| Lotes | planned → active → finished, plantillas ale/lager, un lote activo por tanque, concurrencia optimista | `batches-and-alerts.md` |
| Alertas | Fuera de rango (5 min, histéresis 2 min) y sensor callado (10 min); reconocer; en vivo | `batches-and-alerts.md` |
| Calidad | Perfiles con especificaciones de dos niveles por etapa, plantilla `pale_lager`, perfil por lote, análisis de laboratorio evaluados y guardados (backend + UI) | `batches-and-alerts.md` (T6–T7), `quality-lab-ui.md` |
| Usuarios | Login con sesión en servidor, roles admin/brewer/viewer, contraseña temporal, límite de intentos, página de usuarios | `auth-and-reports.md` |
| Autorización | Sesión en toda la API y WebSockets, roles en escrituras, CSRF, CORS con credenciales | `auth-and-reports.md` |
| Reportes | PDF (WeasyPrint, gráficos SVG) y CSV por lote: estadísticas, % en rango, ABV vs. esperado, alertas, análisis | `auth-and-reports.md` |
| Tanques | Registro automático por primera lectura; el admin los renombra | `quality-lab-ui.md` |
| Simulador | Modelo de fermentación determinista con fallos inyectables | `backend-foundation.md` |

## Evaluación

**Cifras (2026-11-25)**
- Tests: backend 1014, frontend 480, e2e 25 (uno recorre todo el flujo de la tesis), simulador con
  sus propias pruebas.
- Código: ~9.2k líneas de backend y ~12.3k de frontend, con más líneas de tests que de código en el
  backend (~13.6k). 9 migraciones (`0001`–`0009`).

**Fortalezas**
- Arquitectura limpia y consistente: hexagonal en el backend (dominio puro, puertos y adaptadores),
  features con container/presentational en el frontend. Fácil de explicar en la defensa.
- Proceso trazable: cada tarea tiene doc de ODD con decisiones, evidencia de TDD (RED/GREEN) y
  resultado de revisión. Cada commit se revisó por separado (Gentle AI) y los hallazgos se corrigieron o
  se registraron como deuda.
- Specs vivas (`openspec/specs/`) que describen el comportamiento real, no un plan.
- Todo dockerizado: un `docker compose up` levanta el sistema completo en cualquier máquina.
- Seguridad razonable para un MVP: sesiones revocables, Argon2, roles, CSRF, API key de dispositivos,
  un test que falla si una ruta nueva queda sin protección.

**Debilidades y riesgos**
- Solo se probó con sensores simulados: falta validar con hardware real (tiempos, ruido, cortes de WiFi).
- No hay configuración de producción: el compose usa targets `dev` y `--reload`; sin HTTPS, sin retención
  ni compresión de datos en TimescaleDB, sin backups.
- Broker MQTT anónimo (solo desarrollo).
- El alcohol se simula: no existe un sensor casero de % ABV; en la práctica se mide densidad (ver plan
  de hardware).
- Sin prueba con usuarios reales de la cervecería (UX en tablet/celular solo cubierta parcialmente por
  e2e).

## Deuda conocida (no bloqueante)
Detalle completo en cada doc de `odd/tasks/`. Lo principal:
- Seguridad antes de publicar: bloqueo de cuenta ajena por intentos fallidos (el limitador es por proceso),
  `/docs` y `/openapi.json` públicos, Argon2 y render de PDF sin límite de concurrencia, el admin de e2e
  se crea en la base dev con una contraseña pública.
- Funcional: no se guarda quién reconoció una alerta; no se puede editar ni borrar un análisis; sin
  parámetros derivados por fórmula ni gráficos de control; los perfiles de calidad no se pueden borrar.
- UI: si fallan las cargas de plantillas o perfiles, los selects quedan vacíos sin error visible.
- Tests: el e2e no verifica que el análisis aparezca dentro del PDF (lo cubren los tests del backend).

## Próximo paso
1. **Hardware casero** (planificado, sin iniciar): `odd/tasks/esp32-homemade-sensors.md`. Primero hay
   que conseguir los sensores (DS18B20 y transductor de presión).
2. **Publicación**: compose de producción, HTTPS, autenticación en MQTT, retención de datos y la deuda de
   seguridad de arriba.

## Cómo retomar
Ver `AGENTS.md` (también lo carga `CLAUDE.md`): pasos para levantar el entorno, convenciones y, si hay
gentle-ai, `engram sync --import` para traer la memoria.
