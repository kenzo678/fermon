"""Laboratory analyses: one sample of a batch at one stage, judged against the batch's profile."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from fermon.fermentation.domain.batch import Batch, BatchStatus
from fermon.fermentation.domain.errors import (
    InvalidBatchTransitionError,
    InvalidLabAnalysisError,
    InvalidQualityError,
)
from fermon.fermentation.domain.quality import (
    QualityParameter,
    QualityProfile,
    QualityStage,
    QualityStatus,
    check_value,
)

_CATALOG_ORDER = {parameter: index for index, parameter in enumerate(QualityParameter)}


def _parameter(raw: object) -> QualityParameter:
    if isinstance(raw, str):
        try:
            return QualityParameter(raw)
        except ValueError:
            raise InvalidLabAnalysisError(f"values.{raw}", "is not a known parameter") from None
    raise InvalidLabAnalysisError("values", "parameters must be given by their code")


def _value(parameter: QualityParameter, value: object) -> float:
    try:
        return check_value(parameter, value, f"values.{parameter.value}")
    except InvalidQualityError as error:
        raise InvalidLabAnalysisError(error.field, error.reason) from None


def _aware(field: str, value: object) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise InvalidLabAnalysisError(field, "must be a timezone-aware datetime")
    return value


def _optional_text(field: str, value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidLabAnalysisError(field, "must be a string")
    return value.strip() or None


@dataclass(frozen=True, slots=True)
class LabResult:
    """One measured value and how it compared with the spec when it was recorded."""

    parameter: QualityParameter
    value: float
    status: QualityStatus

    def __post_init__(self) -> None:
        parameter = _parameter(self.parameter)
        try:
            status = QualityStatus(self.status)
        except ValueError:
            raise InvalidLabAnalysisError("status", "is not a quality status") from None
        object.__setattr__(self, "parameter", parameter)
        object.__setattr__(self, "value", _value(parameter, self.value))
        object.__setattr__(self, "status", status)


@dataclass(frozen=True, slots=True)
class LabAnalysis:
    """A lab sample of a batch at one stage.

    The statuses are those of the moment it was recorded, against ``quality_profile_id``; they do
    not change if the profile's specs are edited later (it is a quality record).
    """

    id: UUID
    batch_id: UUID
    stage: QualityStage
    sampled_at: datetime
    created_at: datetime
    results: tuple[LabResult, ...]
    analyst: str | None = None
    notes: str | None = None
    quality_profile_id: UUID | None = None

    def __post_init__(self) -> None:
        for field in ("id", "batch_id"):
            if not isinstance(getattr(self, field), UUID):
                raise InvalidLabAnalysisError(field, "must be a UUID")
        if self.quality_profile_id is not None and not isinstance(self.quality_profile_id, UUID):
            raise InvalidLabAnalysisError("quality_profile_id", "must be a UUID")
        try:
            object.__setattr__(self, "stage", QualityStage(self.stage))
        except ValueError:
            choices = ", ".join(stage.value for stage in QualityStage)
            raise InvalidLabAnalysisError("stage", f"must be one of {choices}") from None
        sampled_at = _aware("sampled_at", self.sampled_at)
        created_at = _aware("created_at", self.created_at)
        if sampled_at > created_at:
            raise InvalidLabAnalysisError(
                "sampled_at", "must not be after the analysis is recorded"
            )
        results = tuple(self.results)
        if not results or not all(isinstance(r, LabResult) for r in results):
            raise InvalidLabAnalysisError("values", "needs at least one value")
        if len({r.parameter for r in results}) != len(results):
            raise InvalidLabAnalysisError("values", "each parameter may appear only once")
        object.__setattr__(
            self, "results", tuple(sorted(results, key=lambda r: _CATALOG_ORDER[r.parameter]))
        )
        object.__setattr__(self, "analyst", _optional_text("analyst", self.analyst))
        object.__setattr__(self, "notes", _optional_text("notes", self.notes))


def record_lab_analysis(
    *,
    id: UUID,
    batch: Batch,
    profile: QualityProfile | None,
    stage: QualityStage,
    values: Mapping[QualityParameter | str, object],
    sampled_at: datetime,
    created_at: datetime,
    analyst: str | None = None,
    notes: str | None = None,
) -> LabAnalysis:
    """A new analysis of ``batch``, each value judged against ``profile`` (the batch's own)."""
    if batch.status is BatchStatus.PLANNED:
        # The beer is not brewed yet; filtration and packaging do happen after it finished.
        raise InvalidBatchTransitionError(str(batch.id), batch.status.value, "analyze")
    if (profile.id if profile is not None else None) != batch.quality_profile_id:
        raise InvalidLabAnalysisError("quality_profile_id", "must be the batch's quality profile")
    if not values:
        raise InvalidLabAnalysisError("values", "needs at least one value")
    checked: dict[QualityParameter, float] = {}
    for raw, value in values.items():
        parameter = _parameter(raw)
        checked[parameter] = _value(parameter, value)
    try:
        stage = QualityStage(stage)
    except ValueError:
        raise InvalidLabAnalysisError("stage", "is not a quality stage") from None
    statuses = (
        profile.evaluate(stage, checked)
        if profile is not None
        else dict.fromkeys(checked, QualityStatus.NO_SPEC)
    )
    return LabAnalysis(
        id=id,
        batch_id=batch.id,
        stage=stage,
        sampled_at=sampled_at,
        created_at=created_at,
        results=tuple(LabResult(p, v, statuses[p]) for p, v in checked.items()),
        analyst=analyst,
        notes=notes,
        quality_profile_id=batch.quality_profile_id,
    )
