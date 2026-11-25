import re
import unicodedata

from fermon.fermentation.domain import BatchReport


def _slug(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-") or "beer"


def report_filename(report: BatchReport, extension: str) -> str:
    """``batch-<beer-slug>-<generation date>.<extension>``: ASCII only, safe in a header."""
    return f"batch-{_slug(report.beer_name)}-{report.generated_at:%Y-%m-%d}.{extension}"
