from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from fermon.fermentation.domain import (
    AggregatedPoint,
    Alert,
    AlertKind,
    AlertStatus,
    Batch,
    BatchStatus,
    LabAnalysis,
    LabResult,
    MeasurementType,
    QualityParameter,
    QualityStage,
    QualityStatus,
    StyleTemplate,
    TargetRanges,
    build_batch_report,
    downsample,
    in_range_percent,
)

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
TEMP, PRESSURE, ABV = (
    MeasurementType.TEMPERATURE,
    MeasurementType.PRESSURE,
    MeasurementType.ALCOHOL,
)
TARGETS = TargetRanges(18.0, 21.0, 1.0, None, 5.0)
GAP = timedelta(minutes=10)


def point(
    measurement: MeasurementType, minutes: float, avg: float, count: int = 1, **extra: float
) -> AggregatedPoint:
    return AggregatedPoint(
        T0 + timedelta(minutes=minutes),
        measurement,
        avg,
        extra.get("low", avg),
        extra.get("high", avg),
        count,
    )


def temps(*values: float) -> list[AggregatedPoint]:
    return [point(TEMP, minute, value) for minute, value in enumerate(values)]


def batch(
    status: BatchStatus = BatchStatus.FINISHED,
    finished_at: datetime | None = T0 + timedelta(hours=10),
    expected_end: datetime | None = T0 + timedelta(hours=20),
) -> Batch:
    return Batch(
        id=UUID(int=1),
        tank_id="tank-1",
        beer_name="Pale Ale",
        style="APA",
        template=StyleTemplate.ALE,
        targets=TARGETS,
        status=status,
        planned_start=T0 - timedelta(days=1),
        created_at=T0 - timedelta(days=2),
        expected_end=expected_end,
        started_at=T0,
        finished_at=finished_at if status is BatchStatus.FINISHED else None,
    )


def report(points: list[AggregatedPoint], **overrides: object):  # type: ignore[no-untyped-def]
    args: dict[str, object] = {
        "batch": batch(),
        "profile_name": None,
        "points": points,
        "alerts": [],
        "analyses": [],
        "generated_at": T0 + timedelta(days=1),
        "max_gap": GAP,
    }
    return build_batch_report(**{**args, **overrides})  # type: ignore[arg-type]


# --- time in range -------------------------------------------------------------------------


def test_in_range_is_time_weighted_with_each_sample_holding_until_the_next() -> None:
    # 19 (1 min) + 19 (1 min) + 25 (1 min, out) + 19 (1 min until the window end)
    percent = in_range_percent(temps(19, 19, 25, 19), 18.0, 21.0, T0 + timedelta(minutes=4), GAP)

    assert percent == pytest.approx(75.0)


def test_in_range_weights_by_duration_not_by_sample_count() -> None:
    points = [point(TEMP, 0, 25.0), point(TEMP, 1, 19.0), point(TEMP, 9, 25.0)]

    # out for 1 min, in for 8 min, out for the last 1 min
    assert in_range_percent(points, 18.0, 21.0, T0 + timedelta(minutes=10), GAP) == pytest.approx(
        80.0
    )


def test_in_range_limits_are_inclusive_and_either_side_may_be_open() -> None:
    end = T0 + timedelta(minutes=2)

    assert in_range_percent(temps(18.0, 21.0), 18.0, 21.0, end, GAP) == pytest.approx(100.0)
    assert in_range_percent(temps(0.0, 0.5), None, 1.0, end, GAP) == pytest.approx(100.0)
    assert in_range_percent(temps(5.0, 0.5), None, 1.0, end, GAP) == pytest.approx(50.0)


def test_a_silent_gap_is_capped_and_never_counted_as_in_range() -> None:
    # In range at minute 0, next sample 60 min later: only 10 of those minutes are credited.
    points = [point(TEMP, 0, 19.0), point(TEMP, 60, 25.0)]

    percent = in_range_percent(points, 18.0, 21.0, T0 + timedelta(minutes=61), GAP)

    assert percent == pytest.approx(10 / 11 * 100)


def test_the_last_sample_is_held_until_the_window_end_but_no_longer_than_the_cap() -> None:
    points = [point(TEMP, 0, 25.0), point(TEMP, 1, 19.0)]

    # last sample: window runs 120 min more, only 10 count -> in 10 of 11 observed minutes
    assert in_range_percent(points, 18.0, 21.0, T0 + timedelta(hours=2), GAP) == pytest.approx(
        10 / 11 * 100
    )


def test_in_range_is_none_without_a_target_or_without_samples() -> None:
    end = T0 + timedelta(hours=1)

    assert in_range_percent(temps(19, 19), None, None, end, GAP) is None
    assert in_range_percent([], 18.0, 21.0, end, GAP) is None


def test_samples_before_the_window_start_are_clamped_to_it() -> None:
    # The bucket starts a minute before the window: its first minute is not part of the batch.
    points = [point(TEMP, -1, 25.0), point(TEMP, 1, 19.0)]

    percent = in_range_percent(points, 18.0, 21.0, T0 + timedelta(minutes=2), GAP, start=T0)

    assert percent == pytest.approx(50.0)  # out for [0,1) and in for [1,2)


# --- statistics ----------------------------------------------------------------------------


def test_stats_summarise_each_measurement() -> None:
    result = report(
        [
            point(TEMP, 0, 19.0, count=2, low=18.5, high=19.5),
            point(TEMP, 1, 20.0, count=6, low=19.0, high=21.5),
            point(PRESSURE, 0, 0.8),
        ]
    )

    temperature = next(s for s in result.stats if s.measurement is TEMP)
    assert (temperature.count, temperature.minimum, temperature.maximum) == (8, 18.5, 21.5)
    assert temperature.mean == pytest.approx((19.0 * 2 + 20.0 * 6) / 8)  # weighted by samples
    assert (temperature.first, temperature.last) == (19.0, 20.0)
    assert (temperature.target_min, temperature.target_max) == (18.0, 21.0)
    pressure = next(s for s in result.stats if s.measurement is PRESSURE)
    assert (pressure.target_min, pressure.target_max) == (None, 1.0)
    assert pressure.in_range_percent is not None


def test_alcohol_has_stats_but_no_in_range_percentage() -> None:
    result = report([point(ABV, 0, 0.1), point(ABV, 5, 2.0)])

    (alcohol,) = result.stats
    assert alcohol.measurement is ABV
    assert alcohol.in_range_percent is None
    assert (alcohol.target_min, alcohol.target_max) == (None, None)


def test_a_measurement_without_readings_has_no_stats_and_an_empty_report_is_valid() -> None:
    assert report([]).stats == ()
    assert [s.measurement for s in report(temps(19)).stats] == [TEMP]


# --- window, status and partial reports ------------------------------------------------------


def test_a_finished_report_covers_start_to_finish() -> None:
    result = report(temps(19))

    assert result.window_end == T0 + timedelta(hours=10)
    assert result.duration == timedelta(hours=10)
    assert result.is_partial is False
    assert result.beer_name == "Pale Ale"


def test_an_active_report_is_partial_and_ends_at_generation_time() -> None:
    active = batch(status=BatchStatus.ACTIVE)

    result = report(temps(19), batch=active, generated_at=T0 + timedelta(hours=3))

    assert result.is_partial is True
    assert result.window_end == T0 + timedelta(hours=3)
    assert result.duration == timedelta(hours=3)
    assert result.status_label == "Partial (batch in progress)"


def test_a_planned_batch_cannot_be_reported() -> None:
    planned = Batch(
        id=UUID(int=2),
        tank_id="tank-1",
        beer_name="Stout",
        style="Stout",
        template=StyleTemplate.CUSTOM,
        targets=TARGETS,
        status=BatchStatus.PLANNED,
        planned_start=T0,
        created_at=T0,
    )

    with pytest.raises(Exception, match="planned"):
        report([], batch=planned)


# --- series and the ABV curve ---------------------------------------------------------------


def test_downsample_keeps_short_series_untouched() -> None:
    points = temps(19, 20, 21)

    series = downsample(points, T0, T0 + timedelta(minutes=3), max_points=10)

    assert [(p.at, p.value) for p in series] == [
        (T0, 19.0),
        (T0 + timedelta(minutes=1), 20.0),
        (T0 + timedelta(minutes=2), 21.0),
    ]


def test_downsample_buckets_long_series_to_the_limit_with_weighted_means() -> None:
    points = [point(TEMP, m, float(m % 2), count=1 + m % 2) for m in range(600)]

    series = downsample(points, T0, T0 + timedelta(minutes=600), max_points=100)

    assert 0 < len(series) <= 100
    assert series[0].at == T0
    assert all(a.at < b.at for a, b in zip(series, series[1:], strict=False))
    # the 6-minute buckets mix 0 (count 1) and 1 (count 2): weighted mean 2/3
    assert series[0].value == pytest.approx(2 / 3)


def test_the_expected_abv_rises_linearly_to_the_target_at_the_expected_end() -> None:
    points = [point(ABV, m * 60, 0.5) for m in range(0, 11)]

    result = report(points)  # started T0, expected end T0+20h, target 5.0 %

    assert result.expected_final_abv == 5.0
    by_time = {p.at: p.value for p in result.expected_abv}
    assert by_time[T0] == 0.0
    assert by_time[T0 + timedelta(hours=10)] == pytest.approx(2.5)
    assert max(by_time.values()) <= 5.0


def test_there_is_no_expected_curve_without_an_expected_end_or_final_abv() -> None:
    no_end = report([point(ABV, 0, 0.5)], batch=batch(expected_end=None))
    assert no_end.expected_abv == ()

    assert no_end.expected_final_abv == 5.0  # the target is still reported


# --- alerts and lab analyses -----------------------------------------------------------------


def alert(opened: int, resolved: int | None, **details: str) -> Alert:
    return Alert(
        id=UUID(int=10 + opened),
        tank_id="tank-1",
        batch_id=UUID(int=1),
        kind=AlertKind.OUT_OF_RANGE,
        measurement=TEMP,
        status=AlertStatus.RESOLVED if resolved is not None else AlertStatus.ACKNOWLEDGED,
        opened_at=T0 + timedelta(minutes=opened),
        acknowledged_at=T0 + timedelta(minutes=opened + 1),
        resolved_at=T0 + timedelta(minutes=resolved) if resolved is not None else None,
        details=dict(details),
    )


def test_alerts_are_listed_oldest_first_with_duration_and_resolution() -> None:
    result = report(
        [],
        alerts=[
            alert(90, None),
            alert(10, 25),
            alert(40, 50, resolution="batch_finished"),
        ],
    )

    first, second, third = result.alerts
    assert [a.opened_at for a in result.alerts] == sorted(a.opened_at for a in result.alerts)
    assert (first.duration, first.ongoing, first.resolution) == (
        timedelta(minutes=15),
        False,
        "recovered",
    )
    assert second.resolution == "batch_finished"
    assert (third.ongoing, third.resolved_at, third.resolution) == (True, None, None)
    # ongoing: lasts until the report window ends (finish at +10 h)
    assert third.duration == timedelta(hours=10) - timedelta(minutes=90)
    assert third.acknowledged_at == T0 + timedelta(minutes=91)


def test_lab_analyses_keep_their_stored_statuses() -> None:
    analysis = LabAnalysis(
        id=UUID(int=20),
        batch_id=UUID(int=1),
        stage=QualityStage.MATURATION,
        sampled_at=T0 + timedelta(hours=1),
        created_at=T0 + timedelta(hours=2),
        results=(LabResult(QualityParameter.PH, 4.4, QualityStatus.WARNING),),
        analyst="Ana",
    )

    result = report([], analyses=[analysis], profile_name="Pale lager")

    assert result.profile_name == "Pale lager"
    assert result.analyses == (analysis,)
