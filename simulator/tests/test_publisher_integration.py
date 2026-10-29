import asyncio
import json
import os

import aiomqtt
import pytest

from fermon_simulator.config import Settings
from fermon_simulator.publisher import run_publisher

pytestmark = pytest.mark.integration

HOST = os.environ.get("SIM_MQTT_HOST", "mosquitto")


async def test_publishes_contract_messages_to_broker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIM_MQTT_HOST", HOST)
    monkeypatch.setenv("SIM_TANKS", "it-tank:ale")
    monkeypatch.setenv("SIM_TICK_INTERVAL_SECONDS", "0.1")
    monkeypatch.setenv("SIM_DROPOUT_RATE", "0")
    monkeypatch.setenv("SIM_SPIKE_RATE", "0")
    monkeypatch.setenv("SIM_DISCONNECT_RATE", "0")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    stop = asyncio.Event()
    received: list[tuple[str, dict[str, object]]] = []

    async with aiomqtt.Client(HOST) as subscriber:
        await subscriber.subscribe("fermon/tanks/it-tank/readings", qos=1)
        task = asyncio.create_task(run_publisher(settings, stop))
        try:
            async with asyncio.timeout(10):
                async for message in subscriber.messages:
                    assert isinstance(message.payload, bytes)
                    received.append((str(message.topic), json.loads(message.payload)))
                    if len(received) >= 3:
                        break
        finally:
            stop.set()
            await asyncio.wait_for(task, timeout=10)

    assert {t for t, _ in received} == {"fermon/tanks/it-tank/readings"}
    assert {p["measurement"] for _, p in received} == {"temperature", "pressure", "alcohol"}
    assert all(
        set(p) == {"sensor_id", "measurement", "value", "unit", "recorded_at"} for _, p in received
    )
