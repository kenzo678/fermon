from datetime import UTC, datetime
from uuid import UUID

import pytest

from fermon.identity.domain import (
    InvalidUserError,
    Role,
    Session,
    User,
    WeakPasswordError,
    hash_token,
    normalize_email,
    validate_password,
)

NOW = datetime(2026, 1, 1, 12, tzinfo=UTC)


def make_user(**overrides: object) -> User:
    values: dict[str, object] = {
        "id": UUID(int=1),
        "email": "Ana@Example.com",
        "display_name": "Ana",
        "role": Role.VIEWER,
        "password_hash": "hash",
        "created_at": NOW,
    }
    return User(**{**values, **overrides})  # type: ignore[arg-type]


def test_email_is_trimmed_and_lowercased() -> None:
    assert normalize_email("  Ana@Example.COM ") == "ana@example.com"
    assert make_user().email == "ana@example.com"


@pytest.mark.parametrize("bad", ["", "   ", "no-at-sign", "a@b", "two@@example.com", "a b@c.de"])
def test_invalid_email_is_rejected(bad: str) -> None:
    with pytest.raises(InvalidUserError) as error:
        normalize_email(bad)
    assert error.value.field == "email"


def test_new_user_defaults() -> None:
    user = make_user()
    assert (user.active, user.must_change_password, user.version) == (True, False, 1)


def test_blank_display_name_is_rejected() -> None:
    with pytest.raises(InvalidUserError) as error:
        make_user(display_name="  ")
    assert error.value.field == "display_name"


def test_display_name_is_trimmed() -> None:
    assert make_user(display_name="  Ana  ").display_name == "Ana"


def test_changes_bump_the_version() -> None:
    changed = make_user().changed(role=Role.ADMIN, active=False)
    assert (changed.role, changed.active, changed.version) == (Role.ADMIN, False, 2)


def test_password_needs_at_least_ten_characters() -> None:
    validate_password("x" * 10, "password")
    with pytest.raises(WeakPasswordError) as error:
        validate_password("x" * 9, "new_password")
    assert error.value.field == "new_password"
    assert "10" in str(error.value)


def test_token_hash_is_a_stable_sha256_hex() -> None:
    assert hash_token("abc") == hash_token("abc") != hash_token("abd")
    assert len(hash_token("abc")) == 64


def test_session_validity_window() -> None:
    from datetime import timedelta

    session = Session(
        token_hash="h", user_id=UUID(int=1), created_at=NOW, expires_at=NOW + timedelta(hours=8)
    )
    assert session.is_valid(NOW + timedelta(hours=7, minutes=59))
    assert not session.is_valid(NOW + timedelta(hours=8))
    revoked = session.revoked(NOW)
    assert revoked.revoked_at == NOW and not revoked.is_valid(NOW)
