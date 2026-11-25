import hmac
import logging
from typing import Annotated

from fastapi import Depends, Header
from fastapi.requests import HTTPConnection

from fermon.identity.domain import InvalidDeviceKeyError

logger = logging.getLogger(__name__)


def get_device_api_keys(connection: HTTPConnection) -> list[str]:
    keys: list[str] = connection.app.state.device_api_keys
    return keys


async def require_device_key(
    keys: Annotated[list[str], Depends(get_device_api_keys)],
    x_device_key: Annotated[str | None, Header()] = None,
) -> None:
    """Accept a request only if ``X-Device-Key`` matches one of the configured device keys."""
    if not keys:
        raise InvalidDeviceKeyError("HTTP ingestion is disabled: no device API keys are configured")
    if not x_device_key:
        raise InvalidDeviceKeyError()
    candidate = x_device_key.encode()
    # Check every key (no early exit) with a constant-time comparison.
    matches = [hmac.compare_digest(candidate, key.encode()) for key in keys]
    if not any(matches):
        raise InvalidDeviceKeyError()


def warn_if_device_keys_missing(keys: list[str]) -> None:
    """Startup check: without keys ``POST /readings`` answers 401 (MQTT ingestion is unaffected)."""
    if not keys:
        logger.warning(
            "DEVICE_API_KEYS is empty: HTTP ingestion (POST /readings) is disabled. "
            "Set DEVICE_API_KEYS to a comma-separated list of keys to enable it."
        )
