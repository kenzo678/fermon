import logging

import pytest

from fermon.identity.infrastructure.http.device_key import warn_if_device_keys_missing


def test_no_device_keys_logs_a_startup_warning(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        warn_if_device_keys_missing([])
    assert any(
        r.levelno == logging.WARNING and "DEVICE_API_KEYS" in r.getMessage() for r in caplog.records
    )


def test_configured_device_keys_log_nothing(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        warn_if_device_keys_missing(["key"])
    assert caplog.records == []
