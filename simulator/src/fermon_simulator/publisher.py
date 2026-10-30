"""aiomqtt adapter: publishes every tick, reconnecting with backoff on broker loss."""

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from typing import Any

import aiomqtt

from fermon_simulator.clock import Clock, SimulationClock, SystemClock
from fermon_simulator.config import Settings
from fermon_simulator.faults import FaultInjector
from fermon_simulator.messages import build_message
from fermon_simulator.simulation import generate_tick

logger = logging.getLogger(__name__)

INITIAL_BACKOFF_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 30.0


async def _sleep_or_stop(stop: asyncio.Event, seconds: float) -> None:
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
    except TimeoutError:
        pass


async def run_publisher(
    settings: Settings,
    stop: asyncio.Event,
    clock: Clock | None = None,
    client_factory: Callable[[str, int], Any] = aiomqtt.Client,
    wait: Callable[[asyncio.Event, float], Awaitable[None]] = _sleep_or_stop,
) -> None:
    sim_clock = SimulationClock(settings.acceleration, clock or SystemClock())
    injector = FaultInjector(settings.fault_config(), random.Random(settings.seed))
    tanks = settings.tank_specs
    backoff = INITIAL_BACKOFF_SECONDS
    while not stop.is_set():
        try:
            async with client_factory(settings.mqtt_host, settings.mqtt_port) as client:
                logger.info("connected to %s:%s", settings.mqtt_host, settings.mqtt_port)
                backoff = INITIAL_BACKOFF_SECONDS
                while not stop.is_set():
                    batch = generate_tick(
                        tanks, sim_clock.elapsed_hours(), sim_clock.now(), injector
                    )
                    for tank_id, reading in batch:
                        topic, payload = build_message(tank_id, reading)
                        await client.publish(topic, payload, qos=1)
                    await wait(stop, settings.tick_interval_seconds)
        except aiomqtt.MqttError as exc:
            logger.warning("broker unavailable (%s), retrying in %.0fs", exc, backoff)
            await wait(stop, backoff)
            backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)
