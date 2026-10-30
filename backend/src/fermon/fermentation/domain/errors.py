class DomainError(Exception):
    """Base class for all domain rule violations."""


class InvalidIdentifierError(DomainError):
    """Raised when an identifier (tank, sensor, ...) is not a non-blank string."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(f"invalid {field}: {message}")
        self.field = field
        self.reason = message


class InvalidReadingError(DomainError):
    """Raised when a reading violates a domain invariant."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(f"invalid {field}: {message}")
        self.field = field
        self.reason = message


class InvalidTimeRangeError(DomainError):
    """Raised when a time range is not a timezone-aware, strictly increasing interval."""

    def __init__(self, message: str) -> None:
        super().__init__(f"invalid time range: {message}")


class InvalidTankError(DomainError):
    """Raised when a tank violates a domain invariant."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(f"invalid {field}: {message}")
        self.field = field
        self.reason = message


class TankNotFoundError(DomainError):
    """Raised when a tank that was asked for has never been registered."""

    def __init__(self, tank_id: str) -> None:
        super().__init__(f"tank '{tank_id}' not found")
        self.tank_id = tank_id


class TooManyPointsError(DomainError):
    """Raised when an aggregated query would return more points than allowed."""

    def __init__(self, bucket: str, limit: int) -> None:
        super().__init__(
            f"range too large: more than {limit} points with bucket '{bucket}'; "
            "narrow the range or use a larger bucket"
        )
