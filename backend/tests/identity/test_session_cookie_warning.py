import logging

import pytest

from fermon.identity.infrastructure.http.session_cookie import (
    SessionSettings,
    warn_if_cookie_not_secure,
)


def test_a_non_secure_session_cookie_logs_a_startup_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        warn_if_cookie_not_secure(SessionSettings(ttl_seconds=60, cookie_secure=False))
    assert any(
        r.levelno == logging.WARNING and "SESSION_COOKIE_SECURE" in r.getMessage()
        for r in caplog.records
    )


def test_a_secure_session_cookie_logs_nothing(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        warn_if_cookie_not_secure(SessionSettings(ttl_seconds=60, cookie_secure=True))
    assert caplog.records == []
