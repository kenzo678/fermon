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


async def preflight(
    client: AsyncClient, origin: str, method: str = "GET", request_headers: str | None = None
) -> dict[str, str]:
    headers = {"Origin": origin, "Access-Control-Request-Method": method}
    if request_headers:
        headers["Access-Control-Request-Headers"] = request_headers
    response = await client.options("/health", headers=headers)
    return {"status": str(response.status_code), **dict(response.headers)}


async def test_preflight_from_an_allowed_origin_is_accepted(client: AsyncClient) -> None:
    result = await preflight(client, ALLOWED)

    assert result["status"] == "200"
    assert result["access-control-allow-origin"] == ALLOWED
    assert "GET" in result["access-control-allow-methods"]
    assert result["access-control-allow-credentials"] == "true"


async def test_preflight_from_a_disallowed_origin_is_rejected(client: AsyncClient) -> None:
    result = await preflight(client, DISALLOWED)

    assert result["status"] == "400"
    assert "access-control-allow-origin" not in result


async def test_simple_request_from_an_allowed_origin_gets_the_cors_header(
    client: AsyncClient,
) -> None:
    response = await client.get("/health", headers={"Origin": ALLOWED})

    assert response.headers["access-control-allow-origin"] == ALLOWED


async def test_preflight_allows_put_and_delete_so_browsers_can_edit_quality_specs(
    client: AsyncClient,
) -> None:
    for method in ("PUT", "DELETE"):
        result = await preflight(client, ALLOWED, method=method)

        assert result["status"] == "200", method
        assert method in result["access-control-allow-methods"]


async def test_preflight_allows_patch_so_browsers_can_edit_batches(client: AsyncClient) -> None:
    result = await preflight(client, ALLOWED, method="PATCH")

    assert result["status"] == "200"
    assert "PATCH" in result["access-control-allow-methods"]


async def test_cookies_are_allowed_on_simple_requests_from_an_allowed_origin(
    client: AsyncClient,
) -> None:
    response = await client.get("/health", headers={"Origin": ALLOWED})

    assert response.headers["access-control-allow-credentials"] == "true"
    assert response.headers["access-control-allow-origin"] == ALLOWED  # never "*" with cookies


async def test_preflight_allows_the_csrf_and_device_key_headers(client: AsyncClient) -> None:
    result = await preflight(
        client, ALLOWED, "POST", "content-type, x-requested-with, x-device-key"
    )

    assert result["status"] == "200"
    allowed = result["access-control-allow-headers"].lower()
    for header in ("content-type", "x-requested-with", "x-device-key"):
        assert header in allowed


async def test_preflight_rejects_other_request_headers(client: AsyncClient) -> None:
    result = await preflight(client, ALLOWED, "POST", "authorization")

    assert result["status"] == "400"


async def test_preflight_does_not_offer_unlisted_methods(client: AsyncClient) -> None:
    result = await preflight(client, ALLOWED, "TRACE")

    assert result["status"] == "400"
