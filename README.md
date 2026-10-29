# Fermon

Monitoreo de tanques de fermentación (temperatura, presión y alcohol) para un proyecto de tesis.
Todo el desarrollo se ejecuta dentro de Docker; no se requiere Python en el equipo anfitrión.

## Estructura

- `backend/`: API FastAPI con arquitectura hexagonal (`src/fermon/fermentation/{domain,application,infrastructure}`).
- `mosquitto/`: configuración del broker MQTT (solo para desarrollo).
- `docker-compose.yml`: servicios `api`, `timescaledb` y `mosquitto`.
- `.env.example`: variables de entorno; copiar a `.env` para personalizarlas.

## Comandos de desarrollo

```sh
docker compose up -d                                  # levantar el stack
curl localhost:8000/health                            # {"status": "ok"}
docker compose run --rm api uv run pytest             # pruebas
docker compose run --rm api uv run ruff check .       # lint
docker compose run --rm api uv run ruff format .      # formato
docker compose run --rm api uv run mypy src           # tipos
docker compose down                                   # detener
```
