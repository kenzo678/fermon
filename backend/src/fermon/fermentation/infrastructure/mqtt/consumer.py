"""Inbound MQTT adapter: turns broker messages into ``IngestReading`` calls.

Delivery semantics: the subscription uses QoS 1 and a persistent session (fixed client id,
``clean_session=False``), so the broker queues messages while the ingestor is down and redelivers
unacknowledged ones. QoS 1 is at-least-once; ``IngestReading`` is idempotent on the reading
identity, so redeliveries collapse into effectively-once storage.

Known limitation: aiomqtt acknowledges each message automatically as soon as it is received. If
the database fails while a message is being handled, that message is logged and lost (the broker
already considers it delivered). Future work: manual acknowledgement after the commit.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import aiomqtt
from pydantic import ValidationError

from fermon.fermentation.application import IngestReading
from fermon.fermentation.domain import DomainError
from fermon.fermentation.infrastructure.mqtt.messages import (
    InvalidTopicError,
    ReadingMessage,
    parse_topic,
    to_command,
)
from fermon.shared.config import Settings

logger = logging.getLogger(__name__)

INITIAL_BACKOFF_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 30.0


def _drop(topic: str, reason: str) -> None:
    logger.warning("dropped message topic=%s reason=%s", topic, reason)


async def handle_message(topic: str, payload: bytes | str, ingest: IngestReading) -> None:
    """Validate and ingest one message.

    Invalid messages (topic, JSON, schema, domain rules) are logged and dropped. Unexpected
    errors, such as a database outage, are logged and re-raised for the caller to decide.
    """
    try:
        tank_id = parse_topic(topic)
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
    except Exception:
        logger.exception("failed to ingest message topic=%s", topic)
        raise


def _default_client_factory(settings: Settings) -> Any:
    return aiomqtt.Client(
        settings.mqtt_host,
        settings.mqtt_port,
        identifier=settings.mqtt_client_id,
        clean_session=False,
    )


async def _sleep_or_stop(stop: asyncio.Event, seconds: float) -> None:
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
    except TimeoutError:
        pass


async def _consume(client: Any, ingest: IngestReading, stop: asyncio.Event) -> bool:
    """Handle messages sequentially until stop. Return False if an ingest failed (backoff)."""
    messages = client.messages.__aiter__()
    stop_task = asyncio.ensure_future(stop.wait())
    try:
        while True:
            next_task = asyncio.ensure_future(messages.__anext__())
            await asyncio.wait({next_task, stop_task}, return_when=asyncio.FIRST_COMPLETED)
            if not next_task.done():
                next_task.cancel()
                return True
            try:
                message = next_task.result()
            except StopAsyncIteration:
                return True
            try:
                await handle_message(str(message.topic), message.payload, ingest)
            except Exception:  # already logged by handle_message
                return False
    finally:
        stop_task.cancel()


async def run_consumer(
    settings: Settings,
    ingest: IngestReading,
    stop: asyncio.Event,
    client_factory: Callable[[Settings], Any] = _default_client_factory,
    wait: Callable[[asyncio.Event, float], Awaitable[None]] = _sleep_or_stop,
) -> None:
    """Consume until ``stop`` is set, reconnecting with capped exponential backoff."""
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
                healthy = await _consume(client, ingest, stop)
            if not healthy and not stop.is_set():
                # Ingest failed (e.g. database down): pause so an outage does not spin.
                await wait(stop, backoff)
                backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)
        except aiomqtt.MqttError as exc:
            logger.warning("broker unavailable (%s), retrying in %.0fs", exc, backoff)
            await wait(stop, backoff)
            backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)
