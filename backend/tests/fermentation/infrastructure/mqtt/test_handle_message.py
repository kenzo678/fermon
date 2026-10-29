import json
import logging
from datetime import UTC, datetime
from typing import Any

import pytest

from fermon.fermentation.application import IngestReading
from fermon.fermentation.domain import MeasurementType, Reading
from fermon.fermentation.infrastructure.mqtt.consumer import handle_message
from tests.fermentation.fakes import InMemoryReadingRepository

TOPIC = "fermon/tanks/tank-1/readings"


def payload(**overrides: Any) -> bytes:
    body: dict[str, Any] = {
        "sensor_id": "tank-1-temp",
        "measurement": "temperature",
        "value": 18.5,
        "unit": "celsius",
        "recorded_at": "2026-01-01T12:00:00Z",
    }
    body.update(overrides)
    return json.dumps(body).encode()


class FailingRepository(InMemoryReadingRepository):
    async def add(self, reading: Reading) -> bool:
        raise ConnectionError("database down")


async def test_valid_message_is_ingested() -> None:
    repo = InMemoryReadingRepository()
    await handle_message(TOPIC, payload(), IngestReading(repo))
    assert repo.readings == [
        Reading(
            "tank-1",
            "tank-1-temp",
            MeasurementType.TEMPERATURE,
            18.5,
            "celsius",
            datetime(2026, 1, 1, 12, tzinfo=UTC),
        )
    ]


async def test_duplicate_message_is_stored_once() -> None:
    repo = InMemoryReadingRepository()
    await handle_message(TOPIC, payload(), IngestReading(repo))
    await handle_message(TOPIC, payload(), IngestReading(repo))
    assert len(repo.readings) == 1


@pytest.mark.parametrize(
    ("topic", "body", "reason"),
    [
        (TOPIC, b"{not json", "invalid payload"),
        (TOPIC, payload(extra="x"), "invalid payload"),
        (TOPIC, payload(recorded_at="2026-01-01T12:00:00"), "invalid payload"),
        (TOPIC, payload(value="warm"), "invalid payload"),
        (TOPIC, payload(value=True), "invalid payload"),
        (TOPIC, payload(measurement="humidity"), "unknown measurement"),
        (TOPIC, payload(value=500.0), "value"),
        (TOPIC, payload(unit="kelvin"), "unit"),
        ("fermon/tanks/tank-1/other", payload(), "unexpected topic"),
    ],
)
async def test_invalid_message_is_dropped_with_warning(
    topic: str, body: bytes, reason: str, caplog: pytest.LogCaptureFixture
) -> None:
    repo = InMemoryReadingRepository()
    with caplog.at_level(logging.WARNING):
        await handle_message(topic, body, IngestReading(repo))
    assert repo.readings == []
    [record] = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert topic in record.getMessage()
    assert reason in record.getMessage()


async def test_infrastructure_error_is_logged_and_reraised(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.ERROR), pytest.raises(ConnectionError):
        await handle_message(TOPIC, payload(), IngestReading(FailingRepository()))
    assert any(r.exc_info for r in caplog.records)


async def test_handle_message_validates_against_the_configured_prefix() -> None:
    repo = InMemoryReadingRepository()
    await handle_message(TOPIC, payload(), IngestReading(repo), topic_prefix="fermon-test")
    assert repo.readings == []
    await handle_message(
        "fermon-test/tanks/tank-1/readings",
        payload(),
        IngestReading(repo),
        topic_prefix="fermon-test",
    )
    assert len(repo.readings) == 1
