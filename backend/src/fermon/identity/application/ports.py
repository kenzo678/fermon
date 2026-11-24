from collections.abc import Callable
from datetime import datetime
from typing import Protocol
from uuid import UUID

from fermon.identity.domain import Session, User

Clock = Callable[[], datetime]
"""Returns the current timezone-aware time; injected so expiry rules are testable."""


class PasswordHasher(Protocol):
    """Async because real implementations are CPU-heavy and must not block the event loop."""

    async def hash(self, password: str) -> str: ...

    async def verify(self, password_hash: str, password: str) -> bool: ...

    async def verify_dummy(self, password: str) -> None:
        """Spend the time of one verification, so unknown emails are not distinguishable."""
        ...


class UserRepository(Protocol):
    async def add(self, user: User) -> None:
        """Raises ``EmailAlreadyUsedError`` when the email (case-insensitive) is taken."""
        ...

    async def update(self, user: User) -> None:
        """Writes ``user`` only if the stored version is ``user.version - 1``.

        Raises ``ConcurrentUserUpdateError`` otherwise.
        """
        ...

    async def get(self, user_id: UUID) -> User | None: ...

    async def get_by_email(self, email: str) -> User | None: ...

    async def list(self) -> list[User]: ...

    async def count_active_admins(self) -> int: ...


class SessionStore(Protocol):
    async def add(self, session: Session) -> None: ...

    async def purge_expired(self, now: datetime) -> None:
        """Delete sessions that expired before ``now`` (they can never be used again)."""
        ...

    async def get(self, token_hash: str) -> Session | None: ...

    async def revoke(self, token_hash: str, at: datetime) -> None: ...

    async def revoke_user_sessions(
        self, user_id: UUID, at: datetime, except_token_hash: str | None = None
    ) -> None: ...


class CredentialStore(Protocol):
    """Changes a user's credentials and revokes their sessions as one all-or-nothing write."""

    async def replace_user_and_revoke_sessions(
        self, user: User, at: datetime, except_token_hash: str | None = None
    ) -> None:
        """Writes ``user`` (same optimistic-version rule as ``UserRepository.update``) and revokes
        the user's sessions, except ``except_token_hash``; if either fails, neither is kept."""
        ...
