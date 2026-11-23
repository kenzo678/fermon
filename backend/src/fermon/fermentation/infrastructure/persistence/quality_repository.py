from collections.abc import Sequence
from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fermon.fermentation.domain import (
    DuplicateQualityProfileError,
    QualityParameter,
    QualityProfile,
    QualityProfileNotFoundError,
    QualitySpec,
    QualityStage,
    SpecRange,
)
from fermon.fermentation.infrastructure.persistence.tables import quality_profiles, quality_specs

UNIQUE_NAME_INDEX = "uq_quality_profiles_name"
PROFILE_FOREIGN_KEY = "fk_quality_specs_profile_id"


class SqlAlchemyQualityProfileRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def add(self, profile: QualityProfile) -> None:
        try:
            async with self._session_factory() as session, session.begin():
                await session.execute(
                    quality_profiles.insert().values(
                        id=profile.id,
                        name=profile.name,
                        description=profile.description,
                        created_at=profile.created_at,
                    )
                )
                if profile.specs:
                    await session.execute(
                        quality_specs.insert(), [_spec_row(profile.id, s) for s in profile.specs]
                    )
        except IntegrityError as error:
            if UNIQUE_NAME_INDEX in str(error.orig):
                raise DuplicateQualityProfileError(profile.name) from None
            raise

    # Defined before ``list`` so its annotation refers to the builtin, not to that method.
    async def _load(self, statement: Any) -> list[QualityProfile]:
        """The profiles selected by ``statement`` (in its order), each with its specs."""
        async with self._session_factory() as session:
            profiles = (await session.execute(statement)).all()
            ids = [row.id for row in profiles]
            spec_rows = (
                (
                    await session.execute(
                        select(quality_specs).where(quality_specs.c.profile_id.in_(ids))
                    )
                ).all()
                if ids
                else []
            )
        specs: dict[UUID, list[QualitySpec]] = {profile_id: [] for profile_id in ids}
        for row in spec_rows:
            specs[row.profile_id].append(_spec_from_row(row))
        return [_profile_from_row(row, specs[row.id]) for row in profiles]

    async def get(self, profile_id: UUID) -> QualityProfile | None:
        found = await self._load(
            select(quality_profiles).where(quality_profiles.c.id == profile_id)
        )
        return found[0] if found else None

    async def list(self) -> list[QualityProfile]:
        return await self._load(
            select(quality_profiles).order_by(
                func.lower(quality_profiles.c.name), quality_profiles.c.id
            )
        )

    async def save_spec(self, profile_id: UUID, spec: QualitySpec) -> None:
        row = _spec_row(profile_id, spec)
        statement = insert(quality_specs).values(**row)
        statement = statement.on_conflict_do_update(
            index_elements=["profile_id", "stage", "parameter"],
            set_={k: statement.excluded[k] for k in row if k not in _KEY},
        )
        try:
            async with self._session_factory() as session, session.begin():
                await session.execute(statement)
        except IntegrityError as error:
            if PROFILE_FOREIGN_KEY in str(error.orig):
                raise QualityProfileNotFoundError(str(profile_id)) from None
            raise

    async def delete_spec(
        self, profile_id: UUID, stage: QualityStage, parameter: QualityParameter
    ) -> bool:
        statement = delete(quality_specs).where(
            quality_specs.c.profile_id == profile_id,
            quality_specs.c.stage == stage.value,
            quality_specs.c.parameter == parameter.value,
        )
        async with self._session_factory() as session, session.begin():
            result = await session.execute(statement)
        return cast(CursorResult[Any], result).rowcount > 0


_KEY = frozenset({"profile_id", "stage", "parameter"})


def _spec_row(profile_id: UUID, spec: QualitySpec) -> dict[str, Any]:
    internal = spec.internal or SpecRange()
    return {
        "profile_id": profile_id,
        "stage": spec.stage.value,
        "parameter": spec.parameter.value,
        "target": spec.target,
        "internal_min": internal.minimum,
        "internal_max": internal.maximum,
        "acceptance_min": spec.acceptance.minimum,
        "acceptance_max": spec.acceptance.maximum,
    }


def _spec_from_row(row: Any) -> QualitySpec:
    has_internal = row.internal_min is not None or row.internal_max is not None
    return QualitySpec(
        stage=row.stage,
        parameter=row.parameter,
        acceptance=SpecRange(row.acceptance_min, row.acceptance_max),
        internal=SpecRange(row.internal_min, row.internal_max) if has_internal else None,
        target=row.target,
    )


def _profile_from_row(row: Any, specs: Sequence[QualitySpec]) -> QualityProfile:
    return QualityProfile(
        id=row.id,
        name=row.name,
        description=row.description,
        created_at=row.created_at,
        specs=tuple(specs),
    )
