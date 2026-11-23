from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from fermon.fermentation.domain import (
    DuplicateQualityProfileError,
    QualityParameter,
    QualityProfile,
    QualityProfileNotFoundError,
    QualitySpec,
    QualityStage,
    SpecRange,
)
from fermon.fermentation.infrastructure.persistence import SqlAlchemyQualityProfileRepository

pytestmark = pytest.mark.integration

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
OE_SPEC = QualitySpec(
    QualityStage.BREWHOUSE,
    QualityParameter.ORIGINAL_EXTRACT,
    acceptance=SpecRange(9.9, 10.5),
    internal=SpecRange(10.0, 10.4),
    target=10.2,
)
DIACETYL_SPEC = QualitySpec(
    QualityStage.PACKAGED, QualityParameter.DIACETYL, acceptance=SpecRange(maximum=50.0)
)


def make_profile(n: int, name: str | None = None, *specs: QualitySpec) -> QualityProfile:
    return QualityProfile(
        id=UUID(int=n),
        name=name or f"Profile {n}",
        created_at=T0 + timedelta(minutes=n),
        description=f"profile {n}",
        specs=specs,
    )


async def test_add_then_get_round_trips_the_profile_and_its_specs(
    quality_repository: SqlAlchemyQualityProfileRepository,
) -> None:
    profile = make_profile(1, "Pale lager", OE_SPEC, DIACETYL_SPEC)

    await quality_repository.add(profile)

    assert await quality_repository.get(profile.id) == profile


async def test_get_unknown_profile_is_none(
    quality_repository: SqlAlchemyQualityProfileRepository,
) -> None:
    assert await quality_repository.get(UUID(int=99)) is None


async def test_names_are_unique_ignoring_case(
    quality_repository: SqlAlchemyQualityProfileRepository,
) -> None:
    await quality_repository.add(make_profile(1, "Pale lager"))

    with pytest.raises(DuplicateQualityProfileError):
        await quality_repository.add(make_profile(2, "PALE LAGER"))

    assert await quality_repository.get(UUID(int=2)) is None


async def test_list_orders_by_name_ignoring_case(
    quality_repository: SqlAlchemyQualityProfileRepository,
) -> None:
    for n, name in enumerate(["stout", "Amber", "pale lager"], start=1):
        await quality_repository.add(make_profile(n, name))

    assert [p.name for p in await quality_repository.list()] == ["Amber", "pale lager", "stout"]


async def test_save_spec_inserts_then_replaces(
    quality_repository: SqlAlchemyQualityProfileRepository,
) -> None:
    profile = make_profile(1)
    await quality_repository.add(profile)
    replacement = QualitySpec(
        QualityStage.BREWHOUSE,
        QualityParameter.ORIGINAL_EXTRACT,
        acceptance=SpecRange(minimum=9.5),
    )

    await quality_repository.save_spec(profile.id, OE_SPEC)
    await quality_repository.save_spec(profile.id, replacement)

    stored = await quality_repository.get(profile.id)
    assert stored is not None
    assert stored.specs == (replacement,)


async def test_delete_spec_reports_whether_it_existed(
    quality_repository: SqlAlchemyQualityProfileRepository,
) -> None:
    profile = make_profile(1, None, OE_SPEC, DIACETYL_SPEC)
    await quality_repository.add(profile)

    deleted = await quality_repository.delete_spec(
        profile.id, QualityStage.BREWHOUSE, QualityParameter.ORIGINAL_EXTRACT
    )
    again = await quality_repository.delete_spec(
        profile.id, QualityStage.BREWHOUSE, QualityParameter.ORIGINAL_EXTRACT
    )

    assert (deleted, again) == (True, False)
    stored = await quality_repository.get(profile.id)
    assert stored is not None
    assert stored.specs == (DIACETYL_SPEC,)


async def test_save_spec_for_an_unknown_profile_is_not_found(
    quality_repository: SqlAlchemyQualityProfileRepository,
) -> None:
    with pytest.raises(QualityProfileNotFoundError):
        await quality_repository.save_spec(UUID(int=99), OE_SPEC)


async def test_specs_belong_to_their_own_profile(
    quality_repository: SqlAlchemyQualityProfileRepository,
) -> None:
    await quality_repository.add(make_profile(1, None, OE_SPEC))
    await quality_repository.add(make_profile(2, None, DIACETYL_SPEC))

    profiles = {p.id.int: p.specs for p in await quality_repository.list()}

    assert profiles == {1: (OE_SPEC,), 2: (DIACETYL_SPEC,)}
