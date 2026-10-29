import asyncio
import json
import uuid
from collections.abc import AsyncIterator

import aiomqtt
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from fermon.fermentation.application import IngestReading
from fermon.fermentation.infrastructure.mqtt import run_consumer
from fermon.fermentation.infrastructure.persistence import SqlAlchemyReadingRepository
from fermon.shared.config import Settings

pytestmark = pytest.mark.integration

TOPIC = "fermon/tanks/tank-it/readings"
VALID = {
    "sensor_id": "tank-it-temp",
    "measurement": "temperature",
    "value": 18.5,
    "unit": "celsius",
    "recorded_at": "2026-01-01T12:00:00Z",
}


@pytest.fixture
async def running_consumer(engine: AsyncEngine) -> AsyncIterator[Settings]:
    # Unique client id: a persistent session keyed on a shared id would replay old messages.
    settings = Settings(mqtt_client_id=f"it-{uuid.uuid4().hex[:8]}")
    ingest = IngestReading(
        SqlAlchemyReadingRepository(async_sessionmaker(engine, expire_on_commit=False))
    )
    stop = asyncio.Event()
    task = asyncio.create_task(run_consumer(settings, ingest, stop))
    await asyncio.sleep(1)  # let the consumer subscribe before publishing
    yield settings
    stop.set()
    await asyncio.wait_for(task, timeout=5)


async def publish(settings: Settings, payloads: list[bytes], topic: str = TOPIC) -> None:
    async with aiomqtt.Client(settings.mqtt_host, settings.mqtt_port) as client:
        for body in payloads:
            await client.publish(topic, body, qos=1)


async def count_rows(engine: AsyncEngine) -> int:
    async with engine.connect() as conn:
        return int(await conn.scalar(text("SELECT count(*) FROM readings")) or 0)


async def wait_for_rows(engine: AsyncEngine, expected: int, timeout: float = 10) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while await count_rows(engine) < expected:
        assert loop.time() < deadline, f"expected {expected} rows, got {await count_rows(engine)}"
        await asyncio.sleep(0.1)


async def test_published_reading_is_stored(engine: AsyncEngine, running_consumer: Settings) -> None:
    await publish(running_consumer, [json.dumps(VALID).encode()])
    await wait_for_rows(engine, 1)


async def test_duplicate_and_invalid_messages_do_not_break_the_consumer(
    engine: AsyncEngine, running_consumer: Settings
) -> None:
    valid = json.dumps(VALID).encode()
    second = json.dumps({**VALID, "recorded_at": "2026-01-01T12:00:01Z"}).encode()
    await publish(running_consumer, [valid, valid, b"{broken", b'{"extra": 1}'])
    await publish(running_consumer, [b"{}"], topic="fermon/tanks/tank-it/other")
    await publish(running_consumer, [second])
    await wait_for_rows(engine, 2)
    await asyncio.sleep(0.5)
    assert await count_rows(engine) == 2
