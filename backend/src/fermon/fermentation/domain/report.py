"""Deterministic per-batch report: the numbers behind the PDF and CSV downloads.

Everything here is a pure function of the batch, its readings, alerts and lab analyses. Nothing
reads the clock; ``generated_at`` is given.

Resolution. The readings arrive as 1-minute aggregates (``AggregationBucket.ONE_MINUTE``), never as
raw samples, so a fermentation of weeks stays cheap to report. Each bucket is one *sample* whose
value is the bucket average and whose time is the bucket start. Consequences: ``count`` is the
number of raw readings, ``minimum``/``maximum`` are exact, ``mean`` is weighted by reading count,
and ``first``/``last`` are the averages of the first/last minute with data.

Time in range. Samples are step-held: a sample keeps its value until the next one. A sample is
credited with ``min(time to the next sample, max_gap)``; the last one with ``min(time to the window
end, max_gap)``. Silent periods longer than ``max_gap`` therefore never count as in range, and they
are left out of the denominator too, so the percentage is "of the observed time". A sample is in
range when ``low <= value <= high`` (``None`` bounds are open); without any target it is ``None``.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from fermon.fermentation.domain.aggregation import AggregatedPoint, AggregationBucket
from fermon.fermentation.domain.alert import Alert, AlertKind, AlertStatus
from fermon.fermentation.domain.alert_rules import target_bounds
from fermon.fermentation.domain.batch import Batch, BatchStatus
from fermon.fermentation.domain.errors import InvalidBatchTransitionError
from fermon.fermentation.domain.lab_analysis import LabAnalysis
from fermon.fermentation.domain.measurement import MeasurementType

REPORT_BUCKET = AggregationBucket.ONE_MINUTE
DEFAULT_MAX_GAP = timedelta(minutes=10)
MAX_CHART_POINTS = 240
PARTIAL_LABEL = "Partial (batch in progress)"

_MIN_BUCKET = timedelta(minutes=1)


@dataclass(frozen=True, slots=True)
class SeriesPoint:
    at: datetime
    value: float


@dataclass(frozen=True, slots=True)
class MeasurementStats:
    measurement: MeasurementType
    count: int  # raw readings
    minimum: float
    maximum: float
    mean: float
    first: float
    last: float
    target_min: float | None
    target_max: float | None
    in_range_percent: float | None  # None when there is no target to be in range of
    series: tuple[SeriesPoint, ...]  # downsampled for charts


@dataclass(frozen=True, slots=True)
class ReportAlert:
    id: UUID
    kind: AlertKind
    measurement: MeasurementType | None
    opened_at: datetime
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    duration: timedelta  # up to the end of the report window while ongoing
    ongoing: bool
    resolution: str | None


@dataclass(frozen=True, slots=True)
class BatchReport:
    batch_id: UUID
    beer_name: str
    style: str
    tank_id: str
    status: BatchStatus
    profile_name: str | None
    started_at: datetime
    finished_at: datetime | None
    expected_end: datetime | None
    window_end: datetime
    duration: timedelta
    generated_at: datetime
    max_gap: timedelta
    stats: tuple[MeasurementStats, ...]
    expected_final_abv: float | None
    expected_abv: tuple[SeriesPoint, ...]  # linear 0 -> expected_final_abv by expected_end
    alerts: tuple[ReportAlert, ...]
    analyses: tuple[LabAnalysis, ...]

    @property
    def is_partial(self) -> bool:
        return self.status is BatchStatus.ACTIVE

    @property
    def status_label(self) -> str:
        return PARTIAL_LABEL if self.is_partial else "Complete"


def _sample_times(points: Sequence[AggregatedPoint], start: datetime | None) -> list[datetime]:
    return [max(p.bucket_start, start) if start else p.bucket_start for p in points]


def in_range_percent(
    points: Sequence[AggregatedPoint],
    low: float | None,
    high: float | None,
    window_end: datetime,
    max_gap: timedelta,
    start: datetime | None = None,
) -> float | None:
    """Percentage of the observed time the (single-measurement) samples were within [low, high].

    ``start`` clamps samples whose bucket began before the window. See the module docstring for
    the step-hold and gap-cap rules.
    """
    if (low is None and high is None) or not points:
        return None
    ordered = sorted(points, key=lambda p: p.bucket_start)
    times = _sample_times(ordered, start)
    inside = covered = timedelta()
    for index, sample in enumerate(ordered):
        until = times[index + 1] if index + 1 < len(ordered) else window_end
        held = min(max(until - times[index], timedelta()), max_gap)
        covered += held
        if (low is None or sample.avg >= low) and (high is None or sample.avg <= high):
            inside += held
    if not covered:
        return None
    return inside / covered * 100


def downsample(
    points: Sequence[AggregatedPoint], start: datetime, end: datetime, max_points: int
) -> tuple[SeriesPoint, ...]:
    """At most ``max_points`` points: whole-minute buckets from ``start``, weighted means."""
    ordered = sorted(points, key=lambda p: p.bucket_start)
    if len(ordered) <= max_points:
        return tuple(SeriesPoint(p.bucket_start, p.avg) for p in ordered)
    width = max(math.ceil((end - start) / max_points / _MIN_BUCKET), 1) * _MIN_BUCKET
    sums: dict[int, tuple[float, int]] = {}
    for p in ordered:
        index = max(int((p.bucket_start - start) // width), 0)
        total, count = sums.get(index, (0.0, 0))
        sums[index] = (total + p.avg * p.count, count + p.count)
    return tuple(
        SeriesPoint(start + index * width, total / count)
        for index, (total, count) in sorted(sums.items())
    )


def _bounds(batch: Batch, measurement: MeasurementType) -> tuple[float | None, float | None]:
    if measurement is MeasurementType.ALCOHOL:
        return None, None  # alcohol only shows progress; it has no range to stay in
    return target_bounds(batch.targets, measurement)


def _stats(
    batch: Batch,
    measurement: MeasurementType,
    points: Sequence[AggregatedPoint],
    window_end: datetime,
    max_gap: timedelta,
    max_chart_points: int,
) -> MeasurementStats:
    start = batch.started_at
    assert start is not None
    ordered = sorted(points, key=lambda p: p.bucket_start)
    count = sum(p.count for p in ordered)
    low, high = _bounds(batch, measurement)
    return MeasurementStats(
        measurement=measurement,
        count=count,
        minimum=min(p.min for p in ordered),
        maximum=max(p.max for p in ordered),
        mean=sum(p.avg * p.count for p in ordered) / count,
        first=ordered[0].avg,
        last=ordered[-1].avg,
        target_min=low,
        target_max=high,
        in_range_percent=in_range_percent(ordered, low, high, window_end, max_gap, start),
        series=downsample(ordered, start, window_end, max_chart_points),
    )


def _expected_abv(batch: Batch, at: Sequence[datetime]) -> tuple[SeriesPoint, ...]:
    """Linear expectation: 0 at the start, the target ABV at ``expected_end`` (flat afterwards)."""
    final, start, end = batch.targets.expected_final_abv, batch.started_at, batch.expected_end
    if final is None or start is None or end is None or end <= start:
        return ()
    return tuple(
        SeriesPoint(moment, final * min(max((moment - start) / (end - start), 0.0), 1.0))
        for moment in at
    )


def _alert(alert: Alert, window_end: datetime) -> ReportAlert:
    ended = alert.resolved_at or max(window_end, alert.opened_at)
    resolution = alert.details.get("resolution")
    if resolution is None and alert.status is AlertStatus.RESOLVED:
        resolution = "recovered"
    return ReportAlert(
        id=alert.id,
        kind=alert.kind,
        measurement=alert.measurement,
        opened_at=alert.opened_at,
        acknowledged_at=alert.acknowledged_at,
        resolved_at=alert.resolved_at,
        duration=ended - alert.opened_at,
        ongoing=alert.resolved_at is None,
        resolution=resolution,
    )


def build_batch_report(
    *,
    batch: Batch,
    profile_name: str | None,
    points: Sequence[AggregatedPoint],
    alerts: Sequence[Alert],
    analyses: Sequence[LabAnalysis],
    generated_at: datetime,
    max_gap: timedelta = DEFAULT_MAX_GAP,
    max_chart_points: int = MAX_CHART_POINTS,
) -> BatchReport:
    """The report of a started batch; a planned one has nothing to report (409 over HTTP)."""
    if batch.status is BatchStatus.PLANNED or batch.started_at is None:
        raise InvalidBatchTransitionError(str(batch.id), batch.status.value, "report")
    window_end = max(batch.finished_at or generated_at, batch.started_at)
    by_measurement = {
        m: [p for p in points if p.measurement is m]
        for m in MeasurementType
        if any(p.measurement is m for p in points)
    }
    stats = tuple(
        _stats(batch, m, series, window_end, max_gap, max_chart_points)
        for m, series in by_measurement.items()
    )
    abv = next((s for s in stats if s.measurement is MeasurementType.ALCOHOL), None)
    return BatchReport(
        batch_id=batch.id,
        beer_name=batch.beer_name,
        style=batch.style,
        tank_id=batch.tank_id,
        status=batch.status,
        profile_name=profile_name,
        started_at=batch.started_at,
        finished_at=batch.finished_at,
        expected_end=batch.expected_end,
        window_end=window_end,
        duration=window_end - batch.started_at,
        generated_at=generated_at,
        max_gap=max_gap,
        stats=stats,
        expected_final_abv=batch.targets.expected_final_abv,
        expected_abv=_expected_abv(batch, [p.at for p in abv.series] if abv else []),
        alerts=tuple(sorted((_alert(a, window_end) for a in alerts), key=lambda a: a.opened_at)),
        analyses=tuple(analyses),
    )
