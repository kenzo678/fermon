"""A tiny deterministic SVG line chart (no JavaScript, no plotting library).

The same inputs always give the same bytes: coordinates are rounded to one decimal and nothing
depends on the clock, the locale or the environment.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from html import escape

from fermon.fermentation.domain import SeriesPoint

WIDTH, HEIGHT = 680, 220
_LEFT, _RIGHT, _TOP, _BOTTOM = 52, 14, 36, 30
_TICKS = 5
_BAND_FILL = "#d9efd6"
_TEXT = "#444444"
_GRID = "#e3e3e3"


@dataclass(frozen=True, slots=True)
class ChartSeries:
    label: str
    points: tuple[SeriesPoint, ...]
    color: str
    dashed: bool = False


def _num(value: float) -> str:
    return f"{value:.1f}"


def nice_scale(low: float, high: float) -> tuple[float, float, float]:
    """(axis_min, axis_max, step): a 1/2/2.5/5 x 10^n step, the limits snapped outward to it."""
    if high == low:
        low, high = (max(low - 1.0, 0.0) if low >= 0 else low - 1.0), high + 1.0
    raw = (high - low) / (_TICKS - 1)
    magnitude = 10.0 ** math.floor(math.log10(raw))
    step = next(m * magnitude for m in (1.0, 2.0, 2.5, 5.0, 10.0) if m * magnitude >= raw - 1e-12)
    return (
        round(math.floor(low / step + 1e-9) * step, 10),
        round(math.ceil(high / step - 1e-9) * step, 10),
        step,
    )


def _decimals(step: float) -> int:
    return next(d for d in range(6) if abs(round(step, d) - step) < 1e-9)


def line_chart(
    *,
    title: str,
    unit: str,
    series: Sequence[ChartSeries],
    start: datetime,
    end: datetime,
    band: tuple[float | None, float | None],
) -> str:
    """One chart: ``series`` over [start, end], the target ``band`` (low, high) shaded."""
    plot_w, plot_h = WIDTH - _LEFT - _RIGHT, HEIGHT - _TOP - _BOTTOM
    head = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" '
        f'width="{WIDTH}" height="{HEIGHT}" font-family="DejaVu Sans, Arial, sans-serif">'
    )
    caption = (
        f'<text x="{_LEFT}" y="14" font-size="11" font-weight="bold" fill="{_TEXT}">'
        f"{escape(title)} ({escape(unit)})</text>"
    )
    values = [p.value for line in series for p in line.points]
    if not values:
        empty = (
            f'<text x="{WIDTH / 2}" y="{HEIGHT / 2}" font-size="12" text-anchor="middle" '
            f'fill="{_TEXT}">No data recorded</text>'
        )
        return f"{head}{caption}{empty}</svg>"

    bounds = [b for b in band if b is not None]
    low, high, step = nice_scale(*(lambda v: (min(v), max(v)))(values + bounds))
    decimals = _decimals(step)
    y_ticks = round((high - low) / step)
    span = (end - start).total_seconds() or 1.0

    def x(moment: datetime) -> float:
        fraction = (moment - start).total_seconds() / span
        return _LEFT + min(max(fraction, 0.0), 1.0) * plot_w

    def y(value: float) -> float:
        return _TOP + (1 - (value - low) / (high - low)) * plot_h

    parts = [head, caption]
    if bounds:
        top = y(band[1]) if band[1] is not None else _TOP
        bottom = y(band[0]) if band[0] is not None else _TOP + plot_h
        top, bottom = max(top, _TOP), min(bottom, _TOP + plot_h)
        parts.append(
            f'<rect class="band" x="{_LEFT}" y="{_num(top)}" width="{plot_w}" '
            f'height="{_num(max(bottom - top, 0.0))}" fill="{_BAND_FILL}"/>'
        )
    for index in range(y_ticks + 1):
        value = round(low + index * step, 10)
        parts.append(
            f'<line x1="{_LEFT}" x2="{_LEFT + plot_w}" y1="{_num(y(value))}" y2="{_num(y(value))}" '
            f'stroke="{_GRID}" stroke-width="0.5"/>'
            f'<text x="{_LEFT - 6}" y="{_num(y(value) + 3)}" font-size="9" text-anchor="end" '
            f'fill="{_TEXT}">{value:.{decimals}f}</text>'
        )
    for tick in range(_TICKS):
        moment = start + (end - start) * tick / (_TICKS - 1)
        gx = _LEFT + plot_w * tick / (_TICKS - 1)
        anchor = "end" if tick == _TICKS - 1 else "middle"  # keep the last label inside the SVG
        parts.append(
            f'<text x="{_num(gx)}" y="{HEIGHT - 12}" font-size="9" text-anchor="{anchor}" '
            f'fill="{_TEXT}">{moment:%m-%d %H:%M}</text>'
        )
    legend_x = _LEFT
    for line in series:
        if len(line.points) > 1:
            coordinates = " ".join(f"{_num(x(p.at))},{_num(y(p.value))}" for p in line.points)
            dash = ' stroke-dasharray="5 3"' if line.dashed else ""
            parts.append(
                f'<polyline fill="none" stroke="{line.color}" stroke-width="1.4"{dash} '
                f'points="{coordinates}"/>'
            )
        elif line.points:
            point = line.points[0]
            parts.append(
                f'<circle cx="{_num(x(point.at))}" cy="{_num(y(point.value))}" r="2.5" '
                f'fill="{line.color}"/>'
            )
        if len(series) > 1:  # a lone series is already named by the title
            parts.append(
                f'<text x="{legend_x}" y="26" font-size="9" fill="{line.color}">'
                f"{escape(line.label)}</text>"
            )
            legend_x += 110
    parts.append("</svg>")
    return "".join(parts)
