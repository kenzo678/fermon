import re
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any
from uuid import UUID

from fermon.identity.domain.errors import InvalidUserError, WeakPasswordError
from fermon.identity.domain.role import Role

MIN_PASSWORD_LENGTH = 10
EMAIL_MAX_LENGTH = 254  # RFC 5321 limit of a forward/reverse path
_EMAIL = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")


def normalize_email(value: object) -> str:
    if not isinstance(value, str):
        raise InvalidUserError("email", "must be a string")
    email = value.strip().lower()
    if len(email) > EMAIL_MAX_LENGTH or not _EMAIL.match(email):
        raise InvalidUserError("email", "must be a valid email address")
    return email


def validate_password(password: str, field: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPasswordError(field, f"must have at least {MIN_PASSWORD_LENGTH} characters")


@dataclass(frozen=True, slots=True)
class User:
    id: UUID
    email: str
    display_name: str
    role: Role
    password_hash: str
    created_at: datetime
    must_change_password: bool = False
    active: bool = True
    version: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "email", normalize_email(self.email))
        name = self.display_name.strip() if isinstance(self.display_name, str) else ""
        if not name:
            raise InvalidUserError("display_name", "must not be blank")
        object.__setattr__(self, "display_name", name)
        object.__setattr__(self, "role", Role(self.role))

    def changed(self, **changes: Any) -> "User":
        """A copy with the given fields replaced and the version bumped (optimistic locking)."""
        return replace(self, version=self.version + 1, **changes)
