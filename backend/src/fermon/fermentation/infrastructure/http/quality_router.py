"""Laboratory quality profiles: two-tier specs per stage and parameter, and value evaluation."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, ConfigDict, Field

from fermon.fermentation.application.quality import QualityEvaluation, SaveQualitySpecCommand
from fermon.fermentation.domain import (
    QualityParameter,
    QualityProfile,
    QualitySpec,
    QualityStage,
    QualityTemplate,
    SpecRange,
    quality_template_specs,
)
from fermon.fermentation.infrastructure.http.dependencies import (
    CreateQualityProfileDep,
    EvaluateQualityValuesDep,
    GetQualityProfileDep,
    ListQualityProfilesDep,
    RemoveQualitySpecDep,
    SaveQualitySpecDep,
)
from fermon.fermentation.infrastructure.http.schemas import ErrorResponse

router = APIRouter()

NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}


class QualityParameterOut(BaseModel):
    code: str
    name: str
    unit: str
    minimum: float
    maximum: float


class SpecRangeIO(BaseModel):
    """Inclusive range; an absent bound means no limit on that side."""

    model_config = ConfigDict(extra="forbid")

    min: float | None = None
    max: float | None = None

    def to_domain(self) -> SpecRange:
        return SpecRange(self.min, self.max)

    @classmethod
    def from_domain(cls, spec_range: SpecRange) -> "SpecRangeIO":
        return cls(min=spec_range.minimum, max=spec_range.maximum)


class QualitySpecIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    acceptance: SpecRangeIO
    internal: SpecRangeIO | None = None
    target: float | None = None


class QualitySpecOut(BaseModel):
    stage: str
    parameter: str
    unit: str
    acceptance: SpecRangeIO
    internal: SpecRangeIO | None
    target: float | None

    @classmethod
    def from_domain(cls, spec: QualitySpec) -> "QualitySpecOut":
        return cls(
            stage=spec.stage.value,
            parameter=spec.parameter.value,
            unit=spec.parameter.unit,
            acceptance=SpecRangeIO.from_domain(spec.acceptance),
            internal=None if spec.internal is None else SpecRangeIO.from_domain(spec.internal),
            target=spec.target,
        )


class QualityProfileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str | None = None
    template: QualityTemplate | None = None  # starts the profile with that template's specs


class QualityProfileOut(BaseModel):
    id: UUID
    name: str
    description: str | None
    created_at: datetime
    specs: list[QualitySpecOut]

    @classmethod
    def from_domain(cls, profile: QualityProfile) -> "QualityProfileOut":
        return cls(
            id=profile.id,
            name=profile.name,
            description=profile.description,
            created_at=profile.created_at.astimezone(UTC),
            specs=[QualitySpecOut.from_domain(s) for s in profile.specs],
        )


class QualityTemplateOut(BaseModel):
    template: str
    specs: list[QualitySpecOut]


class EvaluateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: QualityStage
    values: dict[QualityParameter, float] = Field(default_factory=dict)


class EvaluationResultOut(BaseModel):
    parameter: str
    value: float
    unit: str
    status: str

    @classmethod
    def from_domain(cls, evaluation: QualityEvaluation) -> "EvaluationResultOut":
        return cls(
            parameter=evaluation.parameter.value,
            value=evaluation.value,
            unit=evaluation.parameter.unit,
            status=evaluation.status.value,
        )


class EvaluationOut(BaseModel):
    profile_id: UUID
    stage: str
    results: list[EvaluationResultOut]


@router.get("/quality-parameters")
async def list_quality_parameters() -> list[QualityParameterOut]:
    """The catalog of lab parameters, with their unit and physically plausible range."""
    return [
        QualityParameterOut(
            code=p.value, name=p.label, unit=p.unit, minimum=p.limits[0], maximum=p.limits[1]
        )
        for p in QualityParameter
    ]


@router.get("/quality-profile-templates")
async def list_quality_profile_templates() -> list[QualityTemplateOut]:
    """Presets that prefill a new profile's specs: illustrative values meant to be edited."""
    return [
        QualityTemplateOut(
            template=template.value,
            specs=[QualitySpecOut.from_domain(s) for s in quality_template_specs(template)],
        )
        for template in QualityTemplate
    ]


@router.post(
    "/quality-profiles",
    status_code=status.HTTP_201_CREATED,
    responses={409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def create_quality_profile(
    body: QualityProfileIn, use_case: CreateQualityProfileDep
) -> QualityProfileOut:
    """Create a profile, empty or prefilled from `template`.

    409 on `name` if one already has that name (ignoring case).
    """
    profile = await use_case.execute(body.name, body.description, body.template)
    return QualityProfileOut.from_domain(profile)


@router.get("/quality-profiles")
async def list_quality_profiles(use_case: ListQualityProfilesDep) -> list[QualityProfileOut]:
    """Every profile with its specs, by name."""
    return [QualityProfileOut.from_domain(p) for p in await use_case.execute()]


@router.get("/quality-profiles/{profile_id}", responses=NOT_FOUND)
async def get_quality_profile(
    profile_id: UUID, use_case: GetQualityProfileDep
) -> QualityProfileOut:
    """One profile; 404 if unknown."""
    return QualityProfileOut.from_domain(await use_case.execute(profile_id))


@router.put("/quality-profiles/{profile_id}/specs/{stage}/{parameter}", responses=NOT_FOUND)
async def save_quality_spec(
    profile_id: UUID,
    stage: QualityStage,
    parameter: QualityParameter,
    body: QualitySpecIn,
    use_case: SaveQualitySpecDep,
) -> QualitySpecOut:
    """Create or replace the spec of one parameter at one stage.

    `internal` must lie inside `acceptance` and `target` inside the tightest range; 422 names the
    offending field (e.g. `internal.min`).
    """
    command = SaveQualitySpecCommand(
        stage=stage,
        parameter=parameter,
        acceptance=body.acceptance.to_domain(),
        internal=None if body.internal is None else body.internal.to_domain(),
        target=body.target,
    )
    return QualitySpecOut.from_domain(await use_case.execute(profile_id, command))


@router.delete(
    "/quality-profiles/{profile_id}/specs/{stage}/{parameter}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=NOT_FOUND,
)
async def remove_quality_spec(
    profile_id: UUID,
    stage: QualityStage,
    parameter: QualityParameter,
    use_case: RemoveQualitySpecDep,
) -> Response:
    """Remove a spec; 404 on `spec` if the profile has none for that stage and parameter."""
    await use_case.execute(profile_id, stage, parameter)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/quality-profiles/{profile_id}/evaluate", responses=NOT_FOUND)
async def evaluate_quality_values(
    profile_id: UUID, body: EvaluateIn, use_case: EvaluateQualityValuesDep
) -> EvaluationOut:
    """Judge lab values of one stage: `in_spec`, `warning`, `out_of_spec` or `no_spec`."""
    results = await use_case.execute(profile_id, body.stage, body.values)
    return EvaluationOut(
        profile_id=profile_id,
        stage=body.stage.value,
        results=[EvaluationResultOut.from_domain(r) for r in results],
    )
