class DomainError(Exception):
    """Base class for all domain rule violations."""


class InvalidReadingError(DomainError):
    """Raised when a reading violates a domain invariant."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(f"invalid {field}: {message}")
        self.field = field


class InvalidTimeRangeError(DomainError):
    """Raised when a time range is not a timezone-aware, strictly increasing interval."""

    def __init__(self, message: str) -> None:
        super().__init__(f"invalid time range: {message}")
