import asyncio
from functools import cached_property

from argon2 import PasswordHasher as Argon2
from argon2.exceptions import InvalidHashError, VerificationError


class Argon2PasswordHasher:
    """Argon2id with the library's current recommended parameters.

    Argon2 is deliberately slow (tens of milliseconds of CPU), so every call runs in a worker
    thread: doing it inline would freeze the event loop, and with it every other request.
    """

    def __init__(self) -> None:
        self._argon2 = Argon2()

    @cached_property
    def _dummy_hash(self) -> str:
        return self._argon2.hash("fermon-dummy-password")

    async def hash(self, password: str) -> str:
        return await asyncio.to_thread(self._argon2.hash, password)

    async def verify(self, password_hash: str, password: str) -> bool:
        return await asyncio.to_thread(self._verify, password_hash, password)

    async def verify_dummy(self, password: str) -> None:
        await asyncio.to_thread(self._verify_dummy, password)

    def _verify(self, password_hash: str, password: str) -> bool:
        try:
            return self._argon2.verify(password_hash, password)
        except (VerificationError, InvalidHashError):
            return False

    def _verify_dummy(self, password: str) -> None:
        self._verify(self._dummy_hash, password)  # first use also builds the cached dummy hash
