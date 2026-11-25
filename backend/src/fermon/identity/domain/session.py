import hashlib
from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID


def hash_token(token: str) -> str:
    """What is stored for a session token: the token itself never reaches the database."""
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class Session:
    token_hash: str
    user_id: UUID
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None

    def is_valid(self, now: datetime) -> bool:
        return self.revoked_at is None and now < self.expires_at

    def revoked(self, at: datetime) -> "Session":
        return replace(self, revoked_at=self.revoked_at or at)
