from fermon.fermentation.domain import BatchStatus, build_batch_report
from fermon.fermentation.infrastructure.reporting.filename import report_filename
from fermon.fermentation.infrastructure.reporting.pdf_report import render_html, render_pdf
from tests.fermentation.report_samples import sample_batch, sample_report


def test_the_html_has_every_section_of_the_report() -> None:
    html = render_html(sample_report())

    for text in (
        "Pale Ale",
        "APA",
        "tank-1",
        "Pale lager",  # quality profile
        "Complete",
        "Statistics",
        "Alerts",
        "Lab analyses",
        "Out of range",
        "Temperature",
        "Pressure",
        "ABV vs expected",
        "Generated 2026-01-09 08:30 UTC",
    ):
        assert text in html, text
    assert html.count("<svg") == 3


def test_the_html_lists_alert_times_and_lab_values_with_their_stored_status() -> None:
    html = render_html(sample_report())

    assert "2026-01-01 22:00" in html  # alert opened
    assert "2 h" in html  # alert duration
    assert "recovered" in html
    assert "pH" in html and "4.4" in html and "warning" in html
    assert "in spec" in html
    assert "Ana" in html


def test_the_in_range_rule_and_the_resolution_are_stated() -> None:
    html = render_html(sample_report())

    assert "1-minute" in html
    assert "10 min" in html  # the gap cap
    assert "linear" in html


def test_an_active_batch_is_marked_as_partial() -> None:
    html = render_html(sample_report(status=BatchStatus.ACTIVE))

    assert "Partial (batch in progress)" in html


def test_user_text_is_escaped() -> None:
    html = render_html(sample_report(beer_name="<script>alert(1)</script>"))

    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_a_report_without_readings_still_renders() -> None:
    report = sample_report()
    empty = build_batch_report(
        batch=sample_batch(),
        profile_name=None,
        points=[],
        alerts=[],
        analyses=[],
        generated_at=report.generated_at,
    )

    html = render_html(empty)

    assert "No readings were recorded" in html
    assert "No alerts" in html and "No lab analyses" in html
    assert render_pdf(empty).startswith(b"%PDF")


def test_the_pdf_is_a_real_document_and_the_html_is_deterministic() -> None:
    pdf = render_pdf(sample_report())

    assert pdf.startswith(b"%PDF-")
    assert pdf.rstrip().endswith(b"%%EOF")
    assert len(pdf) > 5_000
    assert render_html(sample_report()) == render_html(sample_report())


def test_the_filename_is_a_safe_slug_with_the_generation_date() -> None:
    assert report_filename(sample_report(), "pdf") == "batch-pale-ale-2026-01-09.pdf"
    assert report_filename(sample_report("  Märzen / Ñandú #2! "), "csv") == (
        "batch-marzen-nandu-2-2026-01-09.csv"
    )
    assert report_filename(sample_report("!!!"), "csv") == "batch-beer-2026-01-09.csv"
