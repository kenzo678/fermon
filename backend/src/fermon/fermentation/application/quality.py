from collections.abc import Callable, Mapping
from dataclasses import dataclass
from uuid import UUID, uuid4

from fermon.fermentation.application.batches import Clock
from fermon.fermentation.application.ports import QualityProfileRepository
from fermon.fermentation.domain import (
    QualityParameter,
    QualityProfile,
    QualityProfileNotFoundError,
    QualitySpec,
    QualitySpecNotFoundError,
    QualityStage,
    QualityStatus,
    SpecRange,
    check_value,
)


async def _load(profiles: QualityProfileRepository, profile_id: UUID) -> QualityProfile:
    profile = await profiles.get(profile_id)
    if profile is None:
        raise QualityProfileNotFoundError(str(profile_id))
    return profile


class CreateQualityProfile:
    def __init__(
        self,
        profiles: QualityProfileRepository,
        clock: Clock,
        new_id: Callable[[], UUID] = uuid4,
    ) -> None:
        self._profiles = profiles
        self._clock = clock
        self._new_id = new_id

    async def execute(self, name: str, description: str | None) -> QualityProfile:
        profile = QualityProfile(
            id=self._new_id(), name=name, description=description, created_at=self._clock()
        )
        await self._profiles.add(profile)
        return profile


class GetQualityProfile:
    def __init__(self, profiles: QualityProfileRepository) -> None:
        self._profiles = profiles

    async def execute(self, profile_id: UUID) -> QualityProfile:
        return await _load(self._profiles, profile_id)


class ListQualityProfiles:
    def __init__(self, profiles: QualityProfileRepository) -> None:
        self._profiles = profiles

    async def execute(self) -> list[QualityProfile]:
        return await self._profiles.list()


@dataclass(frozen=True, slots=True)
class SaveQualitySpecCommand:
    stage: QualityStage
    parameter: QualityParameter
    acceptance: SpecRange
    internal: SpecRange | None = None
    target: float | None = None


class SaveQualitySpec:
    """Create or replace the profile's spec for one stage and parameter."""

    def __init__(self, profiles: QualityProfileRepository) -> None:
        self._profiles = profiles

    async def execute(self, profile_id: UUID, command: SaveQualitySpecCommand) -> QualitySpec:
        profile = await _load(self._profiles, profile_id)
        spec = QualitySpec(
            stage=command.stage,
            parameter=command.parameter,
            acceptance=command.acceptance,
            internal=command.internal,
            target=command.target,
        )
        profile.with_spec(spec)  # the profile's own invariants hold with the new spec
        await self._profiles.save_spec(profile.id, spec)
        return spec


class RemoveQualitySpec:
    def __init__(self, profiles: QualityProfileRepository) -> None:
        self._profiles = profiles

    async def execute(
        self, profile_id: UUID, stage: QualityStage, parameter: QualityParameter
    ) -> None:
        await _load(self._profiles, profile_id)
        if not await self._profiles.delete_spec(profile_id, stage, parameter):
            raise QualitySpecNotFoundError(stage.value, parameter.value)


@dataclass(frozen=True, slots=True)
class QualityEvaluation:
    parameter: QualityParameter
    value: float
    status: QualityStatus
    spec: QualitySpec | None


class EvaluateQualityValues:
    """Judge lab values of one stage against a profile, e.g. to flag a form before saving it."""

    def __init__(self, profiles: QualityProfileRepository) -> None:
        self._profiles = profiles

    async def execute(
        self, profile_id: UUID, stage: QualityStage, values: Mapping[QualityParameter, float]
    ) -> list[QualityEvaluation]:
        profile = await _load(self._profiles, profile_id)
        for parameter, value in values.items():
            # Name the offending value by its request path, like any other field error.
            check_value(parameter, value, f"values.{parameter.value}")
        statuses = profile.evaluate(stage, values)
        return [
            QualityEvaluation(
                parameter=parameter,
                value=float(value),
                status=statuses[parameter],
                spec=profile.spec_for(stage, parameter),
            )
            for parameter, value in values.items()
        ]
