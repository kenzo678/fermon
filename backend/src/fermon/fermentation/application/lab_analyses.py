from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from fermon.fermentation.application.batches import Clock
from fermon.fermentation.application.ports import (
    BatchRepository,
    LabAnalysisRepository,
    QualityProfileRepository,
)
from fermon.fermentation.domain import (
    Batch,
    BatchNotFoundError,
    LabAnalysis,
    LabAnalysisNotFoundError,
    QualityParameter,
    QualityProfile,
    QualityProfileNotFoundError,
    QualityStage,
    record_lab_analysis,
)


async def _load_batch(batches: BatchRepository, batch_id: UUID) -> Batch:
    batch = await batches.get(batch_id)
    if batch is None:
        raise BatchNotFoundError(str(batch_id))
    return batch


@dataclass(frozen=True, slots=True)
class RecordLabAnalysisCommand:
    stage: QualityStage
    values: Mapping[QualityParameter | str, object] = field(default_factory=dict)
    sampled_at: datetime | None = None  # defaults to now
    analyst: str | None = None
    notes: str | None = None


class RecordLabAnalysis:
    """Store a lab sample of a batch, each value judged against the batch's quality profile."""

    def __init__(
        self,
        batches: BatchRepository,
        profiles: QualityProfileRepository,
        analyses: LabAnalysisRepository,
        clock: Clock,
        new_id: Callable[[], UUID] = uuid4,
    ) -> None:
        self._batches = batches
        self._profiles = profiles
        self._analyses = analyses
        self._clock = clock
        self._new_id = new_id

    async def execute(self, batch_id: UUID, command: RecordLabAnalysisCommand) -> LabAnalysis:
        batch = await _load_batch(self._batches, batch_id)
        profile = await self._profile_of(batch)
        now = self._clock()
        analysis = record_lab_analysis(
            id=self._new_id(),
            batch=batch,
            profile=profile,
            stage=command.stage,
            values=command.values,
            sampled_at=command.sampled_at or now,
            created_at=now,
            analyst=command.analyst,
            notes=command.notes,
        )
        await self._analyses.add(analysis)
        return analysis

    async def _profile_of(self, batch: Batch) -> QualityProfile | None:
        if batch.quality_profile_id is None:
            return None
        profile = await self._profiles.get(batch.quality_profile_id)
        if profile is None:  # profiles cannot be deleted, so the link should always resolve
            raise QualityProfileNotFoundError(
                str(batch.quality_profile_id), field="quality_profile_id"
            )
        return profile


class ListLabAnalyses:
    def __init__(self, batches: BatchRepository, analyses: LabAnalysisRepository) -> None:
        self._batches = batches
        self._analyses = analyses

    async def execute(self, batch_id: UUID, stage: QualityStage | None = None) -> list[LabAnalysis]:
        """The batch's analyses, oldest sample first; 404 for an unknown batch."""
        await _load_batch(self._batches, batch_id)
        return await self._analyses.list_for_batch(batch_id, stage)


class GetLabAnalysis:
    def __init__(self, analyses: LabAnalysisRepository) -> None:
        self._analyses = analyses

    async def execute(self, analysis_id: UUID) -> LabAnalysis:
        analysis = await self._analyses.get(analysis_id)
        if analysis is None:
            raise LabAnalysisNotFoundError(str(analysis_id))
        return analysis
