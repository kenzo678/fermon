from dataclasses import dataclass
from datetime import datetime

from fermon.fermentation.domain.errors import InvalidIdentifierError, InvalidTankError
from fermon.fermentation.domain.identifier import normalize_id


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
