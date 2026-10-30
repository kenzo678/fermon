"""Inbound MQTT adapter: turns broker messages into ``IngestReading`` calls.

Delivery semantics: the subscription uses QoS 1 and, by default, a persistent session (fixed
client id, ``clean_session=False``), so the broker queues messages while the ingestor is down and
redelivers unacknowledged ones. QoS 1 is at-least-once; ``IngestReading`` is idempotent on the
reading identity, so redeliveries collapse into effectively-once storage.

aiomqtt acknowledges (PUBACK) each message as soon as it is received, so the broker will not
redeliver it. Failures while ingesting are classified (see ``is_transient``):

* Transient (database/network connectivity or availability): the same message is retried in place
  with escalating backoff (1, 2, 4, ... capped at 30 s) while the client stays subscribed and
  aiomqtt keeps buffering later messages.
* Anything else (a poison message, e.g. a constraint violation or a bug): logged at ERROR with the
  traceback, topic and a payload preview, then dropped; the next message is processed at once, so
  one bad message never stalls ingestion.

A message is therefore lost only if the process dies (or stops) while it is being retried, or on a
permanent error. Future work: manual acknowledgement after the commit.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import aiomqtt
from pydantic import ValidationError
from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from fermon.fermentation.application import IngestReading
from fermon.fermentation.domain import DomainError
from fermon.fermentation.infrastructure.mqtt.messages import (
    InvalidTopicError,
    ReadingMessage,
    parse_topic,
    to_command,
)
from fermon.shared.config import Settings
from fermon.shared.waiting import sleep_or_stop

logger = logging.getLogger(__name__)

INITIAL_BACKOFF_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 30.0
DEFAULT_TOPIC_PREFIX = "fermon"
PAYLOAD_PREVIEW_CHARS = 200


def is_transient(exc: BaseException) -> bool:
    """Whether a failure while ingesting is worth retrying on the same message.

    Transient means the database (or network path to it) is unavailable: SQLAlchemy operational,
    interface and connection-invalidated DBAPI errors, OS-level/connection errors, timeouts and
    connection-pool exhaustion (``sqlalchemy.exc.TimeoutError``, which is neither a ``DBAPIError``
    nor the builtin ``TimeoutError``).
    Everything else (integrity violations, programming errors, bugs) would fail identically on
    every retry, so it is permanent.
    """
    if isinstance(
        exc, OperationalError | InterfaceError | OSError | TimeoutError | PoolTimeoutError
    ):
        return True
    return isinstance(exc, DBAPIError) and exc.connection_invalidated


def _payload_preview(payload: object) -> str:
    text = payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else str(payload)
    return text if len(text) <= PAYLOAD_PREVIEW_CHARS else text[:PAYLOAD_PREVIEW_CHARS] + "..."


def _drop(topic: str, reason: str) -> None:
    logger.warning("dropped message topic=%s reason=%s", topic, reason)


async def handle_message(
    topic: str,
    payload: bytes | str,
    ingest: IngestReading,
    topic_prefix: str = DEFAULT_TOPIC_PREFIX,
) -> None:
    """Validate and ingest one message.

    Invalid messages (topic, JSON, schema, domain rules) are logged and dropped. Unexpected
    errors, such as a database outage, are re-raised unlogged for the caller to classify.
    """
    try:
        tank_id = parse_topic(topic, topic_prefix)
        message = ReadingMessage.model_validate_json(payload)
        command = to_command(tank_id, message)
    except InvalidTopicError as exc:
        _drop(topic, str(exc))
        return
    except ValidationError as exc:
        _drop(topic, f"invalid payload: {exc.error_count()} error(s): {exc.errors()[0]['msg']}")
        return
    try:
        await ingest.execute(command)
    except DomainError as exc:
        _drop(topic, str(exc))


def _default_client_factory(settings: Settings) -> Any:
    return aiomqtt.Client(
        settings.mqtt_host,
        settings.mqtt_port,
        identifier=settings.mqtt_client_id,
        clean_session=settings.mqtt_clean_session,
    )


async def _handle_with_retry(
    message: Any,
    ingest: IngestReading,
    stop: asyncio.Event,
    wait: Callable[[asyncio.Event, float], Awaitable[None]],
    topic_prefix: str,
) -> None:
    """Handle one message: retry transient failures in place, drop it on a permanent one."""
    backoff = INITIAL_BACKOFF_SECONDS
    topic = str(message.topic)
    while True:
        try:
            await handle_message(topic, message.payload, ingest, topic_prefix)
            return
        except Exception as exc:
            if not is_transient(exc):
                logger.error(
                    "dropped message after permanent failure topic=%s payload=%s",
                    topic,
                    _payload_preview(message.payload),
                    exc_info=True,
                )
                return
            if stop.is_set():
                break
            logger.warning("retrying message topic=%s in %.0fs after %r", topic, backoff, exc)
            await wait(stop, backoff)
            backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)
            if stop.is_set():
                break
    logger.warning("message not stored (stopped while retrying) topic=%s", topic)


async def _consume(
    client: Any,
    ingest: IngestReading,
    stop: asyncio.Event,
    wait: Callable[[asyncio.Event, float], Awaitable[None]],
    topic_prefix: str,
) -> None:
    """Handle messages sequentially until stop or the stream ends."""
    messages = client.messages.__aiter__()
    stop_task = asyncio.ensure_future(stop.wait())
    try:
        while not stop.is_set():
            next_task = asyncio.ensure_future(messages.__anext__())
            await asyncio.wait({next_task, stop_task}, return_when=asyncio.FIRST_COMPLETED)
            if not next_task.done():
                next_task.cancel()
                return
            try:
                message = next_task.result()
            except StopAsyncIteration:
                return
            await _handle_with_retry(message, ingest, stop, wait, topic_prefix)
    finally:
        stop_task.cancel()


async def run_consumer(
    settings: Settings,
    ingest: IngestReading,
    stop: asyncio.Event,
    client_factory: Callable[[Settings], Any] = _default_client_factory,
    wait: Callable[[asyncio.Event, float], Awaitable[None]] = sleep_or_stop,
    ready: asyncio.Event | None = None,
) -> None:
    """Consume until ``stop`` is set, reconnecting to the broker with capped exponential backoff.

    ``ready`` (optional) is set right after each successful subscribe.
    """
    backoff = INITIAL_BACKOFF_SECONDS
    while not stop.is_set():
        try:
            async with client_factory(settings) as client:
                await client.subscribe(settings.mqtt_topic, qos=1)
                logger.info(
                    "subscribed to %s on %s:%s",
                    settings.mqtt_topic,
                    settings.mqtt_host,
                    settings.mqtt_port,
                )
                backoff = INITIAL_BACKOFF_SECONDS
                if ready is not None:
                    ready.set()
                await _consume(client, ingest, stop, wait, settings.mqtt_topic_prefix)
        except aiomqtt.MqttError as exc:
            logger.warning("broker unavailable (%s), retrying in %.0fs", exc, backoff)
            await wait(stop, backoff)
            backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)
