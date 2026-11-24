from collections.abc import Callable
from uuid import UUID, uuid4

from fermon.identity.application.ports import (
    Clock,
    CredentialStore,
    PasswordHasher,
    SessionStore,
    UserRepository,
)
from fermon.identity.domain import (
    ConcurrentUserUpdateError,
    EmailAlreadyUsedError,
    LastAdminError,
    PermissionDeniedError,
    Role,
    User,
    UserNotFoundError,
    can_manage_users,
    normalize_email,
    validate_password,
)


def _require_admin(actor: User) -> None:
    if not can_manage_users(actor.role):
        raise PermissionDeniedError()


async def _load(users: UserRepository, user_id: UUID) -> User:
    user = await users.get(user_id)
    if user is None:
        raise UserNotFoundError(str(user_id))
    return user


class _NewUser:
    def __init__(
        self,
        users: UserRepository,
        hasher: PasswordHasher,
        clock: Clock,
        new_id: Callable[[], UUID] = uuid4,
    ) -> None:
        self._users = users
        self._hasher = hasher
        self._clock = clock
        self._new_id = new_id

    async def _create(
        self,
        *,
        email: str,
        display_name: str,
        role: Role,
        password: str,
        password_field: str,
        must_change_password: bool,
    ) -> User:
        validate_password(password, password_field)
        email = normalize_email(email)
        if await self._users.get_by_email(email) is not None:
            raise EmailAlreadyUsedError(email)
        user = User(
            id=self._new_id(),
            email=email,
            display_name=display_name,
            role=role,
            password_hash=await self._hasher.hash(password),
            created_at=self._clock(),
            must_change_password=must_change_password,
        )
        await self._users.add(user)  # the unique index is the final word on races
        return user


class CreateUser(_NewUser):
    async def execute(
        self, actor: User, email: str, display_name: str, role: Role, temporary_password: str
    ) -> User:
        _require_admin(actor)
        return await self._create(
            email=email,
            display_name=display_name,
            role=role,
            password=temporary_password,
            password_field="temporary_password",
            must_change_password=True,
        )


class BootstrapAdmin(_NewUser):
    """First administrator, created from the command line (no acting user exists yet)."""

    async def execute(self, email: str, display_name: str, password: str) -> User:
        return await self._create(
            email=email,
            display_name=display_name,
            role=Role.ADMIN,
            password=password,
            password_field="password",
            must_change_password=False,
        )


class ListUsers:
    def __init__(self, users: UserRepository) -> None:
        self._users = users

    async def execute(self, actor: User) -> list[User]:
        _require_admin(actor)
        return await self._users.list()


class UpdateUser:
    def __init__(self, users: UserRepository, sessions: SessionStore, clock: Clock) -> None:
        self._users = users
        self._sessions = sessions
        self._clock = clock

    async def execute(
        self,
        actor: User,
        user_id: UUID,
        version: int,
        role: Role | None = None,
        active: bool | None = None,
        display_name: str | None = None,
    ) -> User:
        _require_admin(actor)
        user = await _load(self._users, user_id)
        if version != user.version:
            raise ConcurrentUserUpdateError(str(user_id))
        changes: dict[str, object] = {}
        if role is not None:
            changes["role"] = role
        if active is not None:
            changes["active"] = active
        if display_name is not None:
            changes["display_name"] = display_name
        updated = user.changed(**changes)
        # Accepted MVP race: the count and the write are separate statements, so two concurrent
        # demotions/deactivations of the last two admins can both pass this guard. A database
        # constraint or row lock would close it; not worth the complexity for a handful of users.
        if _loses_admin(user, updated) and await self._users.count_active_admins() <= 1:
            raise LastAdminError("active" if user.active and not updated.active else "role")
        await self._users.update(updated)
        if user.active and not updated.active:
            await self._sessions.revoke_user_sessions(user.id, self._clock())
        return updated


def _loses_admin(before: User, after: User) -> bool:
    was_active_admin = before.active and before.role is Role.ADMIN
    return was_active_admin and not (after.active and after.role is Role.ADMIN)


class ResetUserPassword:
    def __init__(
        self,
        users: UserRepository,
        hasher: PasswordHasher,
        clock: Clock,
        credentials: CredentialStore,
    ) -> None:
        self._users = users
        self._hasher = hasher
        self._clock = clock
        self._credentials = credentials

    async def execute(self, actor: User, user_id: UUID, temporary_password: str) -> User:
        _require_admin(actor)
        user = await _load(self._users, user_id)
        validate_password(temporary_password, "temporary_password")
        updated = user.changed(
            password_hash=await self._hasher.hash(temporary_password), must_change_password=True
        )
        await self._credentials.replace_user_and_revoke_sessions(updated, self._clock())
        return updated
