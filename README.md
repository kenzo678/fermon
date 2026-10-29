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
docker compose run --rm api uv run pytest             # todas las pruebas (levanta timescaledb)
docker compose run --rm --no-deps api uv run pytest -m "not integration"  # solo unitarias, sin base de datos
docker compose run --rm api uv run alembic upgrade head  # aplicar migraciones
docker compose run --rm api uv run ruff check .       # lint
docker compose run --rm api uv run ruff format .      # formato
docker compose run --rm api uv run mypy src           # tipos
docker compose down                                   # detener
```

Las pruebas de integración usan la base `fermon_test` (se crea sola); se puede cambiar con
`TEST_DATABASE_URL`.
