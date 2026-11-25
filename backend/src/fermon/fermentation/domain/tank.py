from dataclasses import dataclass, replace
from datetime import datetime

from fermon.fermentation.domain.errors import InvalidIdentifierError, InvalidTankError
from fermon.fermentation.domain.identifier import normalize_id

DISPLAY_NAME_MAX_LENGTH = 64


@dataclass(frozen=True, slots=True)
class Tank:
    """A fermentation tank, registered automatically when its first reading arrives."""

    id: str
    display_name: str | None
    first_seen_at: datetime

    def __post_init__(self) -> None:
        try:
            cleaned = normalize_id("id", self.id)
        except InvalidIdentifierError as error:
            raise InvalidTankError(error.field, error.reason) from None
        object.__setattr__(self, "id", cleaned)

        if not isinstance(self.first_seen_at, datetime):
            raise InvalidTankError("first_seen_at", "must be a datetime")
        if self.first_seen_at.tzinfo is None or self.first_seen_at.utcoffset() is None:
            raise InvalidTankError("first_seen_at", "must be timezone-aware")

    def rename(self, display_name: str | None) -> "Tank":
        """The tank with a new display name: trimmed, 1-64 characters, or None to clear it."""
        if display_name is None:
            return replace(self, display_name=None)
        if not isinstance(display_name, str):
            raise InvalidTankError("display_name", "must be a string or null")
        cleaned = display_name.strip()
        if not cleaned:
            raise InvalidTankError("display_name", "must not be blank")
        if len(cleaned) > DISPLAY_NAME_MAX_LENGTH:
            raise InvalidTankError(
                "display_name", f"must be at most {DISPLAY_NAME_MAX_LENGTH} characters"
            )
        return replace(self, display_name=cleaned)
