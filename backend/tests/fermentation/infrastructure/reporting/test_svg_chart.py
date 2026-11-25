import re
from datetime import timedelta

from fermon.fermentation.domain import SeriesPoint
from fermon.fermentation.infrastructure.reporting.svg_chart import (
    ChartSeries,
    line_chart,
    nice_scale,
)
from tests.fermentation.report_samples import T0


def series(*values: float, label: str = "Temperature", dashed: bool = False) -> ChartSeries:
    points = tuple(SeriesPoint(T0 + timedelta(hours=i), v) for i, v in enumerate(values))
    return ChartSeries(label, points, "#1f4e79", dashed)


def chart(*lines: ChartSeries, band: tuple[float | None, float | None] = (None, None)) -> str:
    return line_chart(
        title="Temperature",
        unit="°C",
        series=lines,
        start=T0,
        end=T0 + timedelta(hours=4),
        band=band,
    )


def test_the_chart_is_a_self_contained_svg_with_one_polyline_per_series() -> None:
    svg = chart(series(19.0, 20.0, 19.5), series(18.0, 18.5, label="Expected", dashed=True))

    assert svg.startswith("<svg") and svg.endswith("</svg>")
    assert svg.count("<polyline") == 2
    assert "stroke-dasharray" in svg
    assert "Expected" in svg and "°C" in svg


def test_the_target_band_is_shaded_only_when_there_is_one() -> None:
    assert 'class="band"' in chart(series(19.0, 20.0), band=(18.0, 21.0))
    assert 'class="band"' not in chart(series(19.0, 20.0))
    assert 'class="band"' in chart(series(0.5, 0.7), band=(None, 1.0))  # open on one side


def test_the_output_is_deterministic() -> None:
    first = chart(series(19.0, 20.0, 19.5), band=(18.0, 21.0))

    assert first == chart(series(19.0, 20.0, 19.5), band=(18.0, 21.0))


def test_a_flat_series_and_a_single_point_still_render() -> None:
    assert "<polyline" in chart(series(19.0, 19.0, 19.0))
    assert "<circle" in chart(series(19.0))


def test_without_data_the_chart_says_so() -> None:
    svg = chart(series())

    assert "No data" in svg
    assert "<polyline" not in svg


def test_text_is_escaped() -> None:
    svg = line_chart(
        title="<b>x</b>",
        unit="&",
        series=(),
        start=T0,
        end=T0 + timedelta(hours=1),
        band=(None, None),
    )

    assert "<b>" not in svg and "&lt;b&gt;" in svg


def test_the_axis_does_not_go_below_zero_for_non_negative_data() -> None:
    svg = chart(series(0.0, 0.2, 2.0))

    assert ">-" not in svg


def test_nice_scale_snaps_outward_to_round_steps() -> None:
    low, high, step = nice_scale(17.6, 23.5)

    assert (low, high, step) == (16.0, 24.0, 2.0)  # ticks 16, 18, ... 24
    assert nice_scale(0.55, 1.0)[2] in (0.1, 0.2, 0.25)
    low, high, step = nice_scale(0.0, 5.1)
    assert low == 0.0 and high >= 5.1 and step in (1.0, 2.0)


def test_ticks_are_round_and_the_band_edge_sits_on_its_tick() -> None:
    svg = chart(series(17.6, 23.5, 20.0), band=(18.0, 21.0))

    labels = re.findall(r'text-anchor="end" fill="#444444">([-\d.]+)</text>', svg)
    assert labels and all(float(v) * 2 == int(float(v) * 2) for v in labels)  # halves at worst
    # the pressure case from the PDF: a target max of 1.0 must be a labelled tick
    pressure = chart(series(0.55, 0.65), band=(None, 1.0))
    assert ">1.0<" in pressure or ">1.00<" in pressure
    plot_top = 36.0
    rect_y = float(re.search(r'class="band" x="52" y="([\d.]+)"', pressure).group(1))  # type: ignore[union-attr]
    assert rect_y == plot_top or abs(rect_y - plot_top) < 0.11  # the band top is the axis top


def test_the_legend_has_its_own_row_and_only_exists_for_several_series() -> None:
    single = chart(series(19.0, 20.0))
    double = chart(series(19.0, 20.0), series(18.0, 19.0, label="Expected", dashed=True))

    assert ">Temperature<" not in single.replace("Temperature (", "")
    assert 'y="26"' in double and ">Expected<" in double
