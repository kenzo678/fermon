"""Laboratory analyses of a batch, judged against its quality profile when recorded."""

from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from fermon.fermentation.application.lab_analyses import RecordLabAnalysisCommand
from fermon.fermentation.domain import LabAnalysis, LabResult, QualityStage
from fermon.fermentation.infrastructure.http.dependencies import (
    GetLabAnalysisDep,
    ListLabAnalysesDep,
    RecordLabAnalysisDep,
)
from fermon.fermentation.infrastructure.http.schemas import ErrorResponse
from fermon.identity.domain import can_record_lab_analyses
from fermon.identity.infrastructure.http.dependencies import require_permission

router = APIRouter()

RECORD_ANALYSES = [Depends(require_permission(can_record_lab_analyses))]

ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}


class LabAnalysisIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: QualityStage
    # Keyed by parameter code; unknown codes are reported by the domain as `values.<code>`.
    values: dict[str, float] = Field(default_factory=dict)
    sampled_at: AwareDatetime | None = None
    analyst: str | None = None
    notes: str | None = None


class LabResultOut(BaseModel):
    parameter: str
    value: float
    unit: str
    status: str

    @classmethod
    def from_domain(cls, result: LabResult) -> "LabResultOut":
        return cls(
            parameter=result.parameter.value,
            value=result.value,
            unit=result.parameter.unit,
            status=result.status.value,
        )


class LabAnalysisOut(BaseModel):
    id: UUID
    batch_id: UUID
    stage: str
    sampled_at: datetime
    created_at: datetime
    analyst: str | None
    notes: str | None
    quality_profile_id: UUID | None
    results: list[LabResultOut]

    @classmethod
    def from_domain(cls, analysis: LabAnalysis) -> "LabAnalysisOut":
        return cls(
            id=analysis.id,
            batch_id=analysis.batch_id,
            stage=analysis.stage.value,
            sampled_at=analysis.sampled_at.astimezone(UTC),
            created_at=analysis.created_at.astimezone(UTC),
            analyst=analysis.analyst,
            notes=analysis.notes,
            quality_profile_id=analysis.quality_profile_id,
            results=[LabResultOut.from_domain(r) for r in analysis.results],
        )


@router.post(
    "/batches/{batch_id}/lab-analyses",
    dependencies=RECORD_ANALYSES,
    status_code=status.HTTP_201_CREATED,
    responses=ERRORS,
)
async def record_lab_analysis(
    batch_id: UUID, body: LabAnalysisIn, use_case: RecordLabAnalysisDep
) -> LabAnalysisOut:
    """Record a lab sample of an active or finished batch (409 while it is only planned).

    Each value is judged against the batch's quality profile and the status is stored with it:
    `in_spec`, `warning`, `out_of_spec`, or `no_spec` without a spec. `sampled_at` defaults to now
    and cannot be in the future.
    """
    command = RecordLabAnalysisCommand(
        stage=body.stage,
        values=body.values,
        sampled_at=body.sampled_at,
        analyst=body.analyst,
        notes=body.notes,
    )
    return LabAnalysisOut.from_domain(await use_case.execute(batch_id, command))


@router.get("/batches/{batch_id}/lab-analyses", responses=ERRORS)
async def list_lab_analyses(
    batch_id: UUID,
    use_case: ListLabAnalysesDep,
    stage: Annotated[QualityStage | None, Query()] = None,
) -> list[LabAnalysisOut]:
    """The batch's analyses, oldest sample first, optionally of one stage."""
    return [LabAnalysisOut.from_domain(a) for a in await use_case.execute(batch_id, stage)]


@router.get("/lab-analyses/{analysis_id}", responses=ERRORS)
async def get_lab_analysis(analysis_id: UUID, use_case: GetLabAnalysisDep) -> LabAnalysisOut:
    """One analysis; 404 if unknown."""
    return LabAnalysisOut.from_domain(await use_case.execute(analysis_id))
