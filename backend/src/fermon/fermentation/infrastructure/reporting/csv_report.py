"""The CSV download: a summary section followed by a statistics section (one row per measurement).

The downsampled series, alerts and lab analyses are in the PDF only, so the CSV stays a flat,
spreadsheet-friendly table of the numbers.
"""

import csv
import io
from datetime import datetime

from fermon.fermentation.domain import BatchReport

_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
_STATS_HEADER = [
    "measurement",
    "unit",
    "count",
    "min",
    "max",
    "mean",
    "first",
    "last",
    "target_min",
    "target_max",
    "in_range_percent",
]


def _text(value: str) -> str:
    """Neutralise values a spreadsheet would run as a formula (CSV injection)."""
    return f"'{value}" if value.startswith(_FORMULA_PREFIXES) else value


def _instant(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ") if value else ""


def _number(value: float | None) -> str:
    return "" if value is None else f"{value:.2f}"


def render_csv(report: BatchReport) -> bytes:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["Batch summary"])
    for key, value in (
        ("beer_name", _text(report.beer_name)),
        ("style", _text(report.style)),
        ("tank_id", _text(report.tank_id)),
        ("status", report.status.value),
        ("report", report.status_label),
        ("quality_profile", _text(report.profile_name or "")),
        ("started_at", _instant(report.started_at)),
        ("finished_at", _instant(report.finished_at)),
        ("expected_end", _instant(report.expected_end)),
        ("duration_hours", _number(report.duration.total_seconds() / 3600)),
        ("expected_final_abv", _number(report.expected_final_abv)),
        ("generated_at", _instant(report.generated_at)),
        ("readings_resolution", "1-minute aggregates"),
        ("max_gap_minutes", f"{report.max_gap.total_seconds() / 60:g}"),
    ):
        writer.writerow([key, value])
    writer.writerow([])
    writer.writerow(["Statistics"])
    writer.writerow(_STATS_HEADER)
    for s in report.stats:
        writer.writerow(
            [
                s.measurement.value,
                s.measurement.unit,
                s.count,
                _number(s.minimum),
                _number(s.maximum),
                _number(s.mean),
                _number(s.first),
                _number(s.last),
                _number(s.target_min),
                _number(s.target_max),
                _number(s.in_range_percent),
            ]
        )
    return out.getvalue().encode("utf-8")
