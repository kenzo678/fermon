from httpx import ASGITransport, AsyncClient

from fermon.main import create_app
from fermon.shared.config import Settings

# Nothing listens on port 1: any connection attempt would fail the request.
UNREACHABLE_DATABASE = Settings(database_url="postgresql+asyncpg://nobody:nobody@127.0.0.1:1/none")


async def test_health_works_through_lifespan_without_database_access() -> None:
    app = create_app(UNREACHABLE_DATABASE)

    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
