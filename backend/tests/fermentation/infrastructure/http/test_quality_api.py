from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from fermon.fermentation.application import (
    CreateQualityProfile,
    EvaluateQualityValues,
    GetQualityProfile,
    ListQualityProfiles,
    RemoveQualitySpec,
    SaveQualitySpec,
)
from fermon.fermentation.domain import QualityParameter
from fermon.fermentation.infrastructure.http.dependencies import (
    get_create_quality_profile,
    get_evaluate_quality_values,
    get_get_quality_profile,
    get_list_quality_profiles,
    get_remove_quality_spec,
    get_save_quality_spec,
)
from fermon.main import create_app
from tests.fermentation.fakes import InMemoryQualityProfileRepository

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
OE_SPEC = {
    "acceptance": {"min": 9.9, "max": 10.5},
    "internal": {"min": 10.0, "max": 10.4},
    "target": 10.2,
}


class Ids:
    def __init__(self) -> None:
        self.n = 0

    def __call__(self) -> UUID:
        self.n += 1
        return UUID(int=self.n)


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    profiles = InMemoryQualityProfileRepository()
    ids = Ids()
    app: FastAPI = create_app()
    overrides: Any = app.dependency_overrides
    overrides[get_create_quality_profile] = lambda: CreateQualityProfile(profiles, lambda: T0, ids)
    overrides[get_list_quality_profiles] = lambda: ListQualityProfiles(profiles)
    overrides[get_get_quality_profile] = lambda: GetQualityProfile(profiles)
    overrides[get_save_quality_spec] = lambda: SaveQualitySpec(profiles)
    overrides[get_remove_quality_spec] = lambda: RemoveQualitySpec(profiles)
    overrides[get_evaluate_quality_values] = lambda: EvaluateQualityValues(profiles)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def create_profile(client: AsyncClient, name: str = "Pale lager") -> str:
    response = await client.post("/quality-profiles", json={"name": name, "description": "crisp"})
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def put_oe(client: AsyncClient, profile_id: str, spec: dict[str, Any] = OE_SPEC) -> Any:
    return await client.put(
        f"/quality-profiles/{profile_id}/specs/brewhouse/original_extract", json=spec
    )


def error_fields(response: Any) -> list[str | None]:
    return [d["field"] for d in response.json()["detail"]]


async def test_parameters_catalog(client: AsyncClient) -> None:
    response = await client.get("/quality-parameters")

    assert response.status_code == 200
    catalog = {p["code"]: p for p in response.json()}
    assert len(catalog) == len(QualityParameter)
    assert catalog["original_extract"] == {
        "code": "original_extract",
        "name": "Original extract",
        "unit": "°P",
        "minimum": 0.0,
        "maximum": 30.0,
    }


async def test_create_and_read_a_profile(client: AsyncClient) -> None:
    response = await client.post("/quality-profiles", json={"name": " Pale lager "})

    assert response.status_code == 201
    created = response.json()
    assert created == {
        "id": str(UUID(int=1)),
        "name": "Pale lager",
        "description": None,
        "created_at": "2026-01-01T12:00:00Z",
        "specs": [],
    }
    assert (await client.get(f"/quality-profiles/{created['id']}")).json() == created
    assert (await client.get("/quality-profiles")).json() == [created]


async def test_duplicate_name_is_a_conflict(client: AsyncClient) -> None:
    await create_profile(client)

    response = await client.post("/quality-profiles", json={"name": "PALE LAGER"})

    assert response.status_code == 409
    assert error_fields(response) == ["name"]


async def test_blank_name_is_unprocessable(client: AsyncClient) -> None:
    response = await client.post("/quality-profiles", json={"name": "  "})

    assert response.status_code == 422
    assert error_fields(response) == ["name"]


async def test_unknown_profile_is_not_found(client: AsyncClient) -> None:
    unknown = UUID(int=404)
    for response in (
        await client.get(f"/quality-profiles/{unknown}"),
        await put_oe(client, str(unknown)),
        await client.post(f"/quality-profiles/{unknown}/evaluate", json={"stage": "packaged"}),
    ):
        assert response.status_code == 404, response.text
        assert error_fields(response) == ["profile_id"]


async def test_put_creates_then_replaces_a_spec(client: AsyncClient) -> None:
    profile_id = await create_profile(client)

    created = await put_oe(client, profile_id)
    replaced = await put_oe(client, profile_id, {"acceptance": {"max": 10.6}})

    assert created.status_code == 200
    assert created.json() == {
        "stage": "brewhouse",
        "parameter": "original_extract",
        "unit": "°P",
        "acceptance": {"min": 9.9, "max": 10.5},
        "internal": {"min": 10.0, "max": 10.4},
        "target": 10.2,
    }
    assert replaced.status_code == 200
    specs = (await client.get(f"/quality-profiles/{profile_id}")).json()["specs"]
    assert specs == [
        {
            "stage": "brewhouse",
            "parameter": "original_extract",
            "unit": "°P",
            "acceptance": {"min": None, "max": 10.6},
            "internal": None,
            "target": None,
        }
    ]


async def test_invalid_spec_names_the_offending_field(client: AsyncClient) -> None:
    profile_id = await create_profile(client)

    response = await put_oe(client, profile_id, {**OE_SPEC, "internal": {"min": 9.8, "max": 10.4}})

    assert response.status_code == 422
    assert error_fields(response) == ["internal.min"]


async def test_unknown_stage_or_parameter_in_the_path_is_unprocessable(
    client: AsyncClient,
) -> None:
    profile_id = await create_profile(client)

    bad_stage = await client.put(
        f"/quality-profiles/{profile_id}/specs/mash/original_extract", json=OE_SPEC
    )
    bad_parameter = await client.put(
        f"/quality-profiles/{profile_id}/specs/brewhouse/gravity", json=OE_SPEC
    )

    assert (bad_stage.status_code, error_fields(bad_stage)) == (422, ["stage"])
    assert (bad_parameter.status_code, error_fields(bad_parameter)) == (422, ["parameter"])


async def test_unknown_spec_fields_are_rejected(client: AsyncClient) -> None:
    profile_id = await create_profile(client)

    response = await put_oe(client, profile_id, {**OE_SPEC, "warning": {"max": 1}})

    assert response.status_code == 422
    assert error_fields(response) == ["warning"]


async def test_delete_removes_a_spec_once(client: AsyncClient) -> None:
    profile_id = await create_profile(client)
    await put_oe(client, profile_id)
    path = f"/quality-profiles/{profile_id}/specs/brewhouse/original_extract"

    first = await client.delete(path)
    second = await client.delete(path)

    assert first.status_code == 204
    assert (second.status_code, error_fields(second)) == (404, ["spec"])


async def test_evaluate_judges_each_value(client: AsyncClient) -> None:
    profile_id = await create_profile(client)
    await put_oe(client, profile_id)

    response = await client.post(
        f"/quality-profiles/{profile_id}/evaluate",
        json={"stage": "brewhouse", "values": {"original_extract": 10.45, "ph": 5.2}},
    )

    assert response.status_code == 200
    assert response.json() == {
        "profile_id": profile_id,
        "stage": "brewhouse",
        "results": [
            {"parameter": "original_extract", "value": 10.45, "unit": "°P", "status": "warning"},
            {"parameter": "ph", "value": 5.2, "unit": "pH", "status": "no_spec"},
        ],
    }


async def test_evaluate_rejects_unknown_parameters_and_implausible_values(
    client: AsyncClient,
) -> None:
    profile_id = await create_profile(client)
    path = f"/quality-profiles/{profile_id}/evaluate"

    unknown = await client.post(path, json={"stage": "brewhouse", "values": {"gravity": 1.0}})
    implausible = await client.post(path, json={"stage": "brewhouse", "values": {"ph": 15}})

    assert unknown.status_code == 422
    assert implausible.status_code == 422
    assert error_fields(implausible) == ["values.ph"]
