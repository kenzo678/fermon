from datetime import datetime, timedelta
from uuid import UUID

from fermon.fermentation.application.batches import Clock
from fermon.fermentation.application.ports import (
    AlertRepository,
    BatchRepository,
    LabAnalysisRepository,
    QualityProfileRepository,
    ReadingRepository,
)
from fermon.fermentation.domain import (
    DEFAULT_MAX_GAP,
    REPORT_BUCKET,
    BatchNotFoundError,
    BatchReport,
    BatchStatus,
    InvalidBatchTransitionError,
    MeasurementType,
    build_batch_report,
)


class BuildBatchReport:
    """The deterministic report of an active (partial) or finished batch.

    Statistics come from the readings' 1-minute aggregates over [started_at, finished_at or now].
    """

    def __init__(
        self,
        batches: BatchRepository,
        readings: ReadingRepository,
        alerts: AlertRepository,
        analyses: LabAnalysisRepository,
        profiles: QualityProfileRepository,
        clock: Clock,
        max_gap: timedelta = DEFAULT_MAX_GAP,
    ) -> None:
        self._batches = batches
        self._readings = readings
        self._alerts = alerts
        self._analyses = analyses
        self._profiles = profiles
        self._clock = clock
        self._max_gap = max_gap

    async def execute(self, batch_id: UUID) -> BatchReport:
        batch = await self._batches.get(batch_id)
        if batch is None:
            raise BatchNotFoundError(str(batch_id))
        if batch.status is BatchStatus.PLANNED or batch.started_at is None:
            raise InvalidBatchTransitionError(str(batch.id), batch.status.value, "report")
        now = self._clock()
        end = max(batch.finished_at or now, batch.started_at)
        # Buckets are aligned to the minute: start from the one containing the batch start.
        first_bucket = _floor_to_minute(batch.started_at)
        points = await self._readings.aggregated(
            batch.tank_id,
            REPORT_BUCKET,
            first_bucket,
            max(end, first_bucket + REPORT_BUCKET.interval),
            list(MeasurementType),
        )
        profile = (
            await self._profiles.get(batch.quality_profile_id) if batch.quality_profile_id else None
        )
        return build_batch_report(
            batch=batch,
            profile_name=profile.name if profile else None,
            points=points,
            alerts=await self._alerts.list(batch_id=batch.id),
            analyses=await self._analyses.list_for_batch(batch.id),
            generated_at=now,
            max_gap=self._max_gap,
        )


def _floor_to_minute(moment: datetime) -> datetime:
    return moment.replace(second=0, microsecond=0)
