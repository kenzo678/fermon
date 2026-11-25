class IdentityError(Exception):
    """Base class for identity and access rule violations."""


class InvalidUserError(IdentityError):
    """Raised when a user field violates a domain invariant."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(f"invalid {field}: {message}")
        self.field = field
        self.reason = message


class WeakPasswordError(IdentityError):
    """Raised when a password does not meet the minimum policy."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(f"invalid {field}: {message}")
        self.field = field
        self.reason = message


class InvalidCredentialsError(IdentityError):
    """Authentication failed. The message never says whether the email exists."""

    def __init__(self, message: str = "invalid email or password") -> None:
        super().__init__(message)


class InactiveUserError(InvalidCredentialsError):
    """The user is deactivated; it is reported exactly like invalid credentials."""

    def __init__(self) -> None:
        super().__init__("authentication required")


class PermissionDeniedError(IdentityError):
    """The authenticated user's role does not allow the action."""

    def __init__(self, message: str = "you do not have permission to do this") -> None:
        super().__init__(message)


class MissingCsrfHeaderError(PermissionDeniedError):
    """A state-changing request lacks the ``X-Requested-With: fermon`` header (CSRF defence)."""

    def __init__(self) -> None:
        super().__init__("missing or invalid X-Requested-With header (expected 'fermon')")
        self.field = "X-Requested-With"


class InvalidDeviceKeyError(IdentityError):
    """The ``X-Device-Key`` header is missing or unknown, or no device key is configured."""

    def __init__(self, message: str = "a valid X-Device-Key header is required") -> None:
        super().__init__(message)
        self.field = "X-Device-Key"


class TooManyLoginAttemptsError(IdentityError):
    """Too many recent failed logins for the account or the client address."""

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("too many failed login attempts; try again later")
        self.retry_after_seconds = retry_after_seconds


class PasswordChangeRequiredError(PermissionDeniedError):
    """The account still has a temporary password; only changing it (or signing out) is allowed."""

    def __init__(self) -> None:
        super().__init__("you must change your temporary password before continuing")
        self.field = "password"


class UserNotFoundError(IdentityError):
    def __init__(self, user_id: str) -> None:
        super().__init__(f"user '{user_id}' not found")
        self.user_id = user_id


class EmailAlreadyUsedError(IdentityError):
    def __init__(self, email: str) -> None:
        super().__init__(f"email '{email}' is already registered")
        self.email = email


class ConcurrentUserUpdateError(IdentityError):
    """The user changed since it was read, so writing the stale copy would lose data."""

    def __init__(self, user_id: str) -> None:
        super().__init__(f"user '{user_id}' was modified concurrently; reload and retry")
        self.user_id = user_id


class LastAdminError(IdentityError):
    """The change would leave the system without an active administrator."""

    def __init__(self, field: str = "role") -> None:
        super().__init__("cannot demote or deactivate the last active admin")
        self.field = field  # "role" when demoting, "active" when deactivating
