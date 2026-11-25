import csv
import io

from fermon.fermentation.domain import BatchStatus
from fermon.fermentation.infrastructure.reporting.csv_report import render_csv
from tests.fermentation.report_samples import sample_report


def rows(content: bytes) -> list[list[str]]:
    return list(csv.reader(io.StringIO(content.decode("utf-8"))))


def test_the_csv_has_a_summary_section_then_a_statistics_section() -> None:
    table = rows(render_csv(sample_report()))

    assert table[0] == ["Batch summary"]
    summary = {row[0]: row[1] for row in table[1 : table.index([])]}
    assert summary["beer_name"] == "Pale Ale"
    assert summary["style"] == "APA"
    assert summary["tank_id"] == "tank-1"
    assert summary["status"] == "finished"
    assert summary["report"] == "Complete"
    assert summary["started_at"] == "2026-01-01T12:00:00Z"
    assert summary["finished_at"] == "2026-01-03T12:00:00Z"
    assert summary["duration_hours"] == "48.00"
    assert summary["quality_profile"] == "Pale lager"
    assert summary["generated_at"] == "2026-01-09T08:30:00Z"
    assert summary["readings_resolution"] == "1-minute aggregates"
    assert summary["max_gap_minutes"] == "10"


def test_the_statistics_section_has_one_row_per_measurement() -> None:
    table = rows(render_csv(sample_report()))
    start = table.index(["Statistics"])
    header, *body = table[start + 1 :]

    assert header == [
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
    by_name = {row[0]: dict(zip(header, row, strict=True)) for row in body}
    assert list(by_name) == ["temperature", "pressure", "alcohol"]
    temperature = by_name["temperature"]
    assert temperature["unit"] == "celsius"
    assert temperature["count"] == str(96 * 30)
    assert (temperature["target_min"], temperature["target_max"]) == ("18.00", "21.00")
    assert 0 < float(temperature["in_range_percent"]) < 100
    assert by_name["pressure"]["target_min"] == ""  # no lower pressure target
    assert by_name["alcohol"]["in_range_percent"] == ""  # no range to stay in


def test_an_active_batch_is_marked_partial_and_has_an_empty_end() -> None:
    summary = {
        row[0]: row[1] for row in rows(render_csv(sample_report(status=BatchStatus.ACTIVE)))[1:6]
    }

    assert summary["report"] == "Partial (batch in progress)"


def test_text_that_a_spreadsheet_would_run_as_a_formula_is_neutralised() -> None:
    table = rows(render_csv(sample_report(beer_name="=HYPERLINK(1)")))

    assert ["beer_name", "'=HYPERLINK(1)"] in table


def test_the_output_is_deterministic() -> None:
    assert render_csv(sample_report()) == render_csv(sample_report())
