from starlette.testclient import TestClient

from fermon.main import create_app
from fermon.shared.config import Settings


def test_api_starts_serves_health_and_stops_while_the_database_is_unreachable() -> None:
    # Written after the lifespan wiring (characterization): the listener must never gate startup.
    app = create_app(Settings(database_url="postgresql+asyncpg://u:p@127.0.0.1:1/none"))

    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert app.state.reading_feed is not None
