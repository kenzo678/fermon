class DomainError(Exception):
    """Base class for all domain rule violations."""


class InvalidReadingError(DomainError):
    """Raised when a reading violates a domain invariant."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(f"invalid {field}: {message}")
        self.field = field
