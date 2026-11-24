from datetime import datetime
from uuid import UUID

from fermon.identity.domain import (
    ConcurrentUserUpdateError,
    EmailAlreadyUsedError,
    Role,
    Session,
    User,
)


class FakePasswordHasher:
    """Fast stand-in for Argon2: reversible on purpose, never used outside tests."""

    def __init__(self) -> None:
        self.dummy_verifications = 0
        self.verifications = 0

    async def hash(self, password: str) -> str:
        return f"hashed:{password}"

    async def verify(self, password_hash: str, password: str) -> bool:
        self.verifications += 1
        return password_hash == f"hashed:{password}"

    async def verify_dummy(self, password: str) -> None:
        self.dummy_verifications += 1


class InMemoryUserRepository:
    def __init__(self) -> None:
        self.users: dict[UUID, User] = {}

    async def add(self, user: User) -> None:
        if await self.get_by_email(user.email) is not None:
            raise EmailAlreadyUsedError(user.email)
        self.users[user.id] = user

    async def update(self, user: User) -> None:
        current = self.users.get(user.id)
        if current is None or current.version != user.version - 1:
            raise ConcurrentUserUpdateError(str(user.id))
        self.users[user.id] = user

    async def get(self, user_id: UUID) -> User | None:
        return self.users.get(user_id)

    async def get_by_email(self, email: str) -> User | None:
        return next((u for u in self.users.values() if u.email == email.lower()), None)

    async def list(self) -> list[User]:
        return sorted(self.users.values(), key=lambda u: (u.created_at, u.email))

    async def count_active_admins(self) -> int:
        return sum(1 for u in self.users.values() if u.active and u.role is Role.ADMIN)


class InMemoryCredentialStore:
    """Both writes of a password change; fails before touching either when ``fail`` is set."""

    def __init__(self, users: InMemoryUserRepository, sessions: "InMemorySessionStore") -> None:
        self._users = users
        self._sessions = sessions
        self.fail = False

    async def replace_user_and_revoke_sessions(
        self, user: User, at: datetime, except_token_hash: str | None = None
    ) -> None:
        if self.fail:
            raise RuntimeError("revocation failed")
        await self._users.update(user)
        await self._sessions.revoke_user_sessions(user.id, at, except_token_hash)


class InMemorySessionStore:
    def __init__(self) -> None:
        self.sessions: dict[str, Session] = {}

    async def add(self, session: Session) -> None:
        self.sessions[session.token_hash] = session

    async def get(self, token_hash: str) -> Session | None:
        return self.sessions.get(token_hash)

    async def purge_expired(self, now: datetime) -> None:
        self.sessions = {h: s for h, s in self.sessions.items() if s.expires_at > now}

    async def revoke(self, token_hash: str, at: datetime) -> None:
        if token_hash in self.sessions:
            self.sessions[token_hash] = self.sessions[token_hash].revoked(at)

    async def revoke_user_sessions(
        self, user_id: UUID, at: datetime, except_token_hash: str | None = None
    ) -> None:
        for token_hash, session in list(self.sessions.items()):
            if session.user_id == user_id and token_hash != except_token_hash:
                self.sessions[token_hash] = session.revoked(at)
