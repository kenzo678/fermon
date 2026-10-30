from datetime import datetime

from fermon.fermentation.domain.errors import InvalidTimeRangeError


def validate_time_range(start: datetime, end: datetime) -> None:
    """Ensure ``[start, end)`` is made of timezone-aware datetimes with ``start < end``."""
    for name, moment in (("start", start), ("end", end)):
        if moment.tzinfo is None or moment.utcoffset() is None:
            raise InvalidTimeRangeError(f"{name} must be timezone-aware")
    if start >= end:
        raise InvalidTimeRangeError("start must be before end")
