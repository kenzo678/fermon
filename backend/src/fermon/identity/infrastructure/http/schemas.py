from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from fermon.identity.domain import EMAIL_MAX_LENGTH, Role, User

_PASSWORD = Field(max_length=256)


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(max_length=EMAIL_MAX_LENGTH)
    password: str = _PASSWORD


class ChangePasswordIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = _PASSWORD
    new_password: str = _PASSWORD


class CreateUserIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(max_length=EMAIL_MAX_LENGTH)
    display_name: str = Field(max_length=200)
    role: Role
    temporary_password: str = _PASSWORD


class UpdateUserIn(BaseModel):
    """Partial edit: omitted fields stay as they are; ``version`` is the if-match revision."""

    model_config = ConfigDict(extra="forbid")

    version: int
    role: Role | None = None
    active: bool | None = None
    display_name: str | None = Field(default=None, max_length=200)


class ResetPasswordIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    temporary_password: str = _PASSWORD


class UserOut(BaseModel):
    """Public view of a user: never carries the password hash."""

    id: UUID
    email: str
    display_name: str
    role: Role
    must_change_password: bool
    active: bool
    version: int

    @classmethod
    def from_domain(cls, user: User) -> "UserOut":
        return cls(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            role=user.role,
            must_change_password=user.must_change_password,
            active=user.active,
            version=user.version,
        )


class SessionOut(BaseModel):
    user: UserOut
