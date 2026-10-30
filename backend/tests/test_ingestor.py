import asyncio
import logging
from pathlib import Path
from typing import Any

import pytest

from fermon.fermentation.application import IngestReading
from fermon.fermentation.infrastructure.schema import SchemaCheckError, SchemaState
from fermon.ingestor import main, run
from fermon.shared.config import Settings


class FakeEngine:
    def __init__(self) -> None:
        self.disposed = False

    async def dispose(self) -> None:
        self.disposed = True


class Harness:
    """Records the ingestor collaborators' calls; ``schema_results`` scripts the schema check."""

    def __init__(self, schema_results: list[SchemaState]) -> None:
        self.schema_results = schema_results
        self.engine = FakeEngine()
        self.events: list[str] = []
        self.checked_with: list[tuple[Any, Any]] = []
        self.consumer_calls = 0
        self.settings = Settings(alembic_ini_path=Path("/custom/alembic.ini"))

    def engine_factory(self, settings: Settings) -> Any:
        return self.engine

    async def schema_check(self, engine: Any, config: Any) -> SchemaState:
        self.checked_with.append((engine, config))
        self.events.append("check")
        return self.schema_results.pop(0)

    async def wait_for_schema(self, check: Any, stop: asyncio.Event) -> bool:
        while not stop.is_set():
            if await check() is SchemaState.READY:
                return True
            self.events.append("waiting")
            await asyncio.sleep(0)
        return False

    async def consumer(
        self, settings: Settings, ingest: IngestReading, stop: asyncio.Event
    ) -> None:
        self.events.append("consumer")
        self.consumer_calls += 1

    async def run(self, stop: asyncio.Event) -> None:
        await run(
            self.settings,
            stop,
            engine_factory=self.engine_factory,
            schema_check=self.schema_check,
            wait_for=self.wait_for_schema,
            consumer=self.consumer,
        )


async def test_consumer_starts_only_after_the_schema_is_ready() -> None:
    harness = Harness([SchemaState.BEHIND, SchemaState.BEHIND, SchemaState.READY])
    await harness.run(asyncio.Event())
    assert harness.events == ["check", "waiting", "check", "waiting", "check", "consumer"]
    assert harness.engine.disposed is True


async def test_consumer_is_never_started_when_stopped_while_waiting() -> None:
    stop = asyncio.Event()
    harness = Harness([SchemaState.BEHIND] * 5)
    original = harness.schema_check

    async def check_then_stop(engine: Any, config: Any) -> SchemaState:
        stop.set()
        return await original(engine, config)

    harness.schema_check = check_then_stop  # type: ignore[method-assign]
    await harness.run(stop)
    assert harness.consumer_calls == 0
    assert harness.engine.disposed is True


async def test_schema_check_is_bound_to_the_engine_and_configured_ini_path() -> None:
    harness = Harness([SchemaState.READY])
    await harness.run(asyncio.Event())
    [(engine, config)] = harness.checked_with
    assert engine is harness.engine
    assert Path(config.config_file_name) == Path("/custom/alembic.ini")


async def test_engine_is_disposed_when_the_schema_check_is_fatal() -> None:
    harness = Harness([])

    async def failing_wait(check: Any, stop: asyncio.Event) -> bool:
        raise SchemaCheckError("boom")

    harness.wait_for_schema = failing_wait  # type: ignore[method-assign]
    with pytest.raises(SchemaCheckError):
        await harness.run(asyncio.Event())
    assert harness.consumer_calls == 0
    assert harness.engine.disposed is True


async def test_main_logs_schema_check_errors_and_returns_non_zero(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def failing_run(settings: Settings, stop: asyncio.Event) -> None:
        raise SchemaCheckError("database is at revision abc which this code does not know")

    with caplog.at_level(logging.ERROR):
        assert await main(Settings(), runner=failing_run) != 0
    errors = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1
    assert "does not know" in errors[0]


async def test_main_returns_zero_on_clean_shutdown() -> None:
    async def ok_run(settings: Settings, stop: asyncio.Event) -> None:
        return None

    assert await main(Settings(), runner=ok_run) == 0
