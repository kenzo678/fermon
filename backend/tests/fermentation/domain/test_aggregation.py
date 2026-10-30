from datetime import UTC, datetime, timedelta

import pytest

from fermon.fermentation.domain import (
    AggregatedPoint,
    AggregationBucket,
    InvalidTimeRangeError,
    MeasurementType,
    TooManyPointsError,
    validate_aggregation_range,
)

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def test_bucket_values_and_intervals() -> None:
    assert AggregationBucket("1m") is AggregationBucket.ONE_MINUTE
    assert AggregationBucket("1h") is AggregationBucket.ONE_HOUR
    assert AggregationBucket.ONE_MINUTE.interval == timedelta(minutes=1)
    assert AggregationBucket.ONE_HOUR.interval == timedelta(hours=1)


def test_aggregated_point_is_a_value_object() -> None:
    point = AggregatedPoint(T0, MeasurementType.TEMPERATURE, 18.5, 18.0, 19.0, 4)

    assert (point.bucket_start, point.avg, point.min, point.max, point.count) == (
        T0,
        18.5,
        18.0,
        19.0,
        4,
    )


def test_range_at_the_limit_is_accepted() -> None:
    validate_aggregation_range(T0, T0 + timedelta(minutes=10_000), AggregationBucket.ONE_MINUTE)


def test_range_over_the_limit_is_rejected_with_a_clear_message() -> None:
    with pytest.raises(TooManyPointsError, match="10000.*1m"):
        validate_aggregation_range(T0, T0 + timedelta(minutes=10_001), AggregationBucket.ONE_MINUTE)


def test_hourly_buckets_allow_a_much_longer_range() -> None:
    validate_aggregation_range(T0, T0 + timedelta(days=300), AggregationBucket.ONE_HOUR)


def test_invalid_range_is_rejected_first() -> None:
    with pytest.raises(InvalidTimeRangeError):
        validate_aggregation_range(T0, T0, AggregationBucket.ONE_MINUTE)
