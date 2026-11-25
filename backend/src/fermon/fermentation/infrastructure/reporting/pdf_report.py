"""The PDF download: an HTML template (Jinja2) printed to A4 by WeasyPrint.

Charts are inline SVG drawn by ``svg_chart``; there is no JavaScript and no plotting library, so
the same report always renders the same document.
"""

from datetime import datetime, timedelta
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup
from weasyprint import HTML  # type: ignore[import-untyped]

from fermon.fermentation.domain import BatchReport, MeasurementStats, MeasurementType
from fermon.fermentation.infrastructure.reporting.svg_chart import ChartSeries, line_chart

_TEMPLATES = Path(__file__).parent / "templates"
_OBSERVED, _EXPECTED = "#1f4e79", "#c4620a"
_TITLES = {
    MeasurementType.TEMPERATURE: "Temperature",
    MeasurementType.PRESSURE: "Pressure",
    MeasurementType.ALCOHOL: "ABV vs expected",
}


def _duration(value: timedelta) -> str:
    minutes = int(value.total_seconds() // 60)
    days, minutes = divmod(minutes, 24 * 60)
    hours, minutes = divmod(minutes, 60)
    parts = [f"{n} {unit}" for n, unit in ((days, "d"), (hours, "h"), (minutes, "min")) if n]
    return " ".join(parts) or "0 min"


def _moment(value: datetime | None) -> str:
    return f"{value:%Y-%m-%d %H:%M}" if value else "-"


def _number(value: float | None, digits: int = 2) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def _environment() -> Environment:
    env = Environment(
        loader=FileSystemLoader(_TEMPLATES),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters.update(duration=_duration, moment=_moment, number=_number)
    return env


_ENV = _environment()


def _chart(report: BatchReport, stats: MeasurementStats) -> Markup:
    lines = [ChartSeries(_TITLES[stats.measurement], stats.series, _OBSERVED)]
    if stats.measurement is MeasurementType.ALCOHOL and report.expected_abv:
        lines.append(ChartSeries("Expected", report.expected_abv, _EXPECTED, dashed=True))
    return Markup(  # noqa: S704 - markup built by svg_chart, which escapes its text
        line_chart(
            title=_TITLES[stats.measurement],
            unit=stats.measurement.unit,
            series=lines,
            start=report.started_at,
            end=report.window_end,
            band=(stats.target_min, stats.target_max),
        )
    )


def render_html(report: BatchReport) -> str:
    charts = [(_TITLES[s.measurement], _chart(report, s)) for s in report.stats]
    return _ENV.get_template("report.html").render(
        report=report,
        charts=charts,
        generated=f"{report.generated_at:%Y-%m-%d %H:%M} UTC",
    )


def render_pdf(report: BatchReport) -> bytes:
    pdf: bytes = HTML(string=render_html(report)).write_pdf()
    return pdf
