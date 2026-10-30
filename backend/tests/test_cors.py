from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from fermon.main import create_app
from fermon.shared.config import Settings

ALLOWED = "http://localhost:5173"
DISALLOWED = "http://evil.example"


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app(Settings(cors_origins=[ALLOWED]))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def preflight(client: AsyncClient, origin: str, method: str = "GET") -> dict[str, str]:
    response = await client.options(
        "/health", headers={"Origin": origin, "Access-Control-Request-Method": method}
    )
    return {"status": str(response.status_code), **dict(response.headers)}


async def test_preflight_from_an_allowed_origin_is_accepted(client: AsyncClient) -> None:
    result = await preflight(client, ALLOWED)

    assert result["status"] == "200"
    assert result["access-control-allow-origin"] == ALLOWED
    assert "GET" in result["access-control-allow-methods"]
    assert "access-control-allow-credentials" not in result


async def test_preflight_from_a_disallowed_origin_is_rejected(client: AsyncClient) -> None:
    result = await preflight(client, DISALLOWED)

    assert result["status"] == "400"
    assert "access-control-allow-origin" not in result


async def test_simple_request_from_an_allowed_origin_gets_the_cors_header(
    client: AsyncClient,
) -> None:
    response = await client.get("/health", headers={"Origin": ALLOWED})

    assert response.headers["access-control-allow-origin"] == ALLOWED
