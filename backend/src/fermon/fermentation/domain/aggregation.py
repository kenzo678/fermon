from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from fermon.fermentation.domain.errors import TooManyPointsError
from fermon.fermentation.domain.measurement import MeasurementType
from fermon.fermentation.domain.time_range import validate_time_range

# A chart cannot usefully draw more points than this, and it bounds the work of one request.
MAX_POINTS = 10_000


class AggregationBucket(StrEnum):
    ONE_MINUTE = "1m"
    ONE_HOUR = "1h"

    @property
    def interval(self) -> timedelta:
        return _INTERVALS[self]


_INTERVALS: dict[AggregationBucket, timedelta] = {
    AggregationBucket.ONE_MINUTE: timedelta(minutes=1),
    AggregationBucket.ONE_HOUR: timedelta(hours=1),
}


@dataclass(frozen=True, slots=True)
class AggregatedPoint:
    """Statistics of one measurement of one tank over a bucket (all its sensors together)."""

    bucket_start: datetime
    measurement: MeasurementType
    avg: float
    min: float
    max: float
    count: int


def validate_aggregation_range(start: datetime, end: datetime, bucket: AggregationBucket) -> None:
    """Validate ``[start, end)`` and reject ranges that would return more than ``MAX_POINTS``."""
    validate_time_range(start, end)
    if (end - start) / bucket.interval > MAX_POINTS:
        raise TooManyPointsError(bucket.value, MAX_POINTS)
