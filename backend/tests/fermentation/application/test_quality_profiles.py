from datetime import UTC, datetime
from uuid import UUID

import pytest

from fermon.fermentation.application import (
    CreateQualityProfile,
    EvaluateQualityValues,
    GetQualityProfile,
    ListQualityProfiles,
    RemoveQualitySpec,
    SaveQualitySpec,
    SaveQualitySpecCommand,
)
from fermon.fermentation.domain import (
    DuplicateQualityProfileError,
    InvalidQualityError,
    QualityParameter,
    QualityProfileNotFoundError,
    QualitySpec,
    QualitySpecNotFoundError,
    QualityStage,
    QualityStatus,
    SpecRange,
)
from tests.fermentation.fakes import InMemoryQualityProfileRepository

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
OE = QualityParameter.ORIGINAL_EXTRACT
PH = QualityParameter.PH
BREWHOUSE = QualityStage.BREWHOUSE
UNKNOWN = UUID(int=404)

OE_COMMAND = SaveQualitySpecCommand(
    stage=BREWHOUSE,
    parameter=OE,
    acceptance=SpecRange(9.9, 10.5),
    internal=SpecRange(10.0, 10.4),
    target=10.2,
)


@pytest.fixture
def repository() -> InMemoryQualityProfileRepository:
    return InMemoryQualityProfileRepository()


async def create(repository: InMemoryQualityProfileRepository, name: str = "Pale lager") -> UUID:
    use_case = CreateQualityProfile(repository, clock=lambda: T0, new_id=lambda: UUID(int=1))
    return (await use_case.execute(name, "crisp")).id


async def test_create_stores_an_empty_profile(repository: InMemoryQualityProfileRepository) -> None:
    use_case = CreateQualityProfile(repository, clock=lambda: T0, new_id=lambda: UUID(int=7))

    profile = await use_case.execute(" Pale lager ", " crisp ")

    assert (profile.id, profile.name, profile.description) == (UUID(int=7), "Pale lager", "crisp")
    assert profile.created_at == T0
    assert profile.specs == ()
    assert await repository.get(UUID(int=7)) == profile


async def test_create_rejects_a_duplicate_name(
    repository: InMemoryQualityProfileRepository,
) -> None:
    await create(repository)
    use_case = CreateQualityProfile(repository, clock=lambda: T0, new_id=lambda: UUID(int=2))

    with pytest.raises(DuplicateQualityProfileError):
        await use_case.execute("pale LAGER", None)


async def test_get_and_list(repository: InMemoryQualityProfileRepository) -> None:
    profile_id = await create(repository)

    assert (await GetQualityProfile(repository).execute(profile_id)).name == "Pale lager"
    assert [p.id for p in await ListQualityProfiles(repository).execute()] == [profile_id]
    with pytest.raises(QualityProfileNotFoundError):
        await GetQualityProfile(repository).execute(UNKNOWN)


async def test_save_spec_validates_and_stores_it(
    repository: InMemoryQualityProfileRepository,
) -> None:
    profile_id = await create(repository)

    spec = await SaveQualitySpec(repository).execute(profile_id, OE_COMMAND)

    assert spec == QualitySpec(BREWHOUSE, OE, SpecRange(9.9, 10.5), SpecRange(10.0, 10.4), 10.2)
    stored = await repository.get(profile_id)
    assert stored is not None and stored.specs == (spec,)


async def test_save_spec_rejects_an_invalid_spec_without_storing_it(
    repository: InMemoryQualityProfileRepository,
) -> None:
    profile_id = await create(repository)
    bad = SaveQualitySpecCommand(BREWHOUSE, OE, acceptance=SpecRange(9.9, 10.5),
                                 internal=SpecRange(9.0, 10.4))  # fmt: skip

    with pytest.raises(InvalidQualityError):
        await SaveQualitySpec(repository).execute(profile_id, bad)

    stored = await repository.get(profile_id)
    assert stored is not None and stored.specs == ()


async def test_save_spec_for_an_unknown_profile_is_not_found(
    repository: InMemoryQualityProfileRepository,
) -> None:
    with pytest.raises(QualityProfileNotFoundError):
        await SaveQualitySpec(repository).execute(UNKNOWN, OE_COMMAND)


async def test_remove_spec(repository: InMemoryQualityProfileRepository) -> None:
    profile_id = await create(repository)
    await SaveQualitySpec(repository).execute(profile_id, OE_COMMAND)
    remove = RemoveQualitySpec(repository)

    await remove.execute(profile_id, BREWHOUSE, OE)

    stored = await repository.get(profile_id)
    assert stored is not None and stored.specs == ()
    with pytest.raises(QualitySpecNotFoundError):
        await remove.execute(profile_id, BREWHOUSE, OE)
    with pytest.raises(QualityProfileNotFoundError):
        await remove.execute(UNKNOWN, BREWHOUSE, OE)


async def test_evaluate_returns_one_result_per_value_in_the_order_sent(
    repository: InMemoryQualityProfileRepository,
) -> None:
    profile_id = await create(repository)
    await SaveQualitySpec(repository).execute(profile_id, OE_COMMAND)

    results = await EvaluateQualityValues(repository).execute(
        profile_id, BREWHOUSE, {PH: 5.2, OE: 10.45}
    )

    assert [(r.parameter, r.value, r.status) for r in results] == [
        (PH, 5.2, QualityStatus.NO_SPEC),
        (OE, 10.45, QualityStatus.WARNING),
    ]
    assert results[0].spec is None
    assert results[1].spec is not None and results[1].spec.target == 10.2


async def test_evaluate_reports_implausible_values_by_their_request_path(
    repository: InMemoryQualityProfileRepository,
) -> None:
    profile_id = await create(repository)

    with pytest.raises(InvalidQualityError) as error:
        await EvaluateQualityValues(repository).execute(profile_id, BREWHOUSE, {PH: 15.0})

    assert error.value.field == "values.ph"


async def test_evaluate_for_an_unknown_profile_is_not_found(
    repository: InMemoryQualityProfileRepository,
) -> None:
    with pytest.raises(QualityProfileNotFoundError):
        await EvaluateQualityValues(repository).execute(UNKNOWN, BREWHOUSE, {OE: 10.2})
