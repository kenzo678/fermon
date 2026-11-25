import threading
from typing import Any

from fermon.identity.infrastructure.hashing import Argon2PasswordHasher


async def test_hash_is_argon2id_salted_and_verifiable() -> None:
    hasher = Argon2PasswordHasher()
    first, second = await hasher.hash("correct horse"), await hasher.hash("correct horse")
    assert first.startswith("$argon2id$") and first != second
    assert await hasher.verify(first, "correct horse")
    assert not await hasher.verify(first, "wrong horse")


async def test_verify_treats_a_malformed_hash_as_a_mismatch() -> None:
    assert not await Argon2PasswordHasher().verify("not-a-hash", "whatever")


async def test_dummy_verification_runs_without_matching_anything() -> None:
    await Argon2PasswordHasher().verify_dummy("whatever")


class _ThreadRecorder:
    """Stands in for the Argon2 library and remembers which thread each call ran on."""

    def __init__(self) -> None:
        self.threads: list[int] = []

    def hash(self, password: str) -> str:
        self.threads.append(threading.get_ident())
        return "hash"

    def verify(self, password_hash: str, password: str) -> bool:
        self.threads.append(threading.get_ident())
        return True


async def test_hashing_and_verifying_never_block_the_event_loop_thread() -> None:
    hasher = Argon2PasswordHasher()
    recorder: Any = _ThreadRecorder()
    hasher._argon2 = recorder

    await hasher.hash("password-123")
    await hasher.verify("hash", "password-123")
    await hasher.verify_dummy("password-123")

    assert len(recorder.threads) == 4  # hash, verify, then dummy: hash + verify
    assert threading.get_ident() not in recorder.threads
