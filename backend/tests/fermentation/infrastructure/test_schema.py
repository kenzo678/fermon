import asyncio
import logging
from pathlib import Path

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from alembic.util.exc import CommandError
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine

from fermon.fermentation.infrastructure.schema import (
    SchemaCheckError,
    SchemaState,
    alembic_config,
    classify_revision,
    schema_state,
    wait_for_schema,
)

READY = SchemaState.READY
BEHIND = SchemaState.BEHIND
UNKNOWN = SchemaState.UNKNOWN_REVISION


class Script:
    """Scripted ``check`` plus a fake ``wait`` that records delays and yields to the loop."""

    def __init__(self, results: list[SchemaState | BaseException]) -> None:
        self.results = results
        self.waits: list[float] = []

    async def check(self) -> SchemaState:
        result = self.results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result

    async def wait(self, stop: asyncio.Event, seconds: float) -> None:
        self.waits.append(seconds)
        await asyncio.sleep(0)


async def test_returns_true_without_waiting_when_already_ready() -> None:
    script = Script([READY])
    assert await wait_for_schema(script.check, asyncio.Event(), script.wait) is True
    assert script.waits == []


async def test_waits_with_escalating_backoff_until_ready(
    caplog: pytest.LogCaptureFixture,
) -> None:
    script = Script([BEHIND, BEHIND, BEHIND, READY])
    with caplog.at_level(logging.INFO):
        assert await wait_for_schema(script.check, asyncio.Event(), script.wait) is True
    assert script.waits == [1, 2, 4]
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 3
    assert all("alembic upgrade head" in r.getMessage() for r in warnings)
    assert any(r.levelno == logging.INFO and "ready" in r.getMessage() for r in caplog.records)


async def test_backoff_is_capped_at_30_seconds() -> None:
    script = Script([BEHIND] * 8 + [READY])
    assert await wait_for_schema(script.check, asyncio.Event(), script.wait) is True
    assert script.waits == [1, 2, 4, 8, 16, 30, 30, 30]


async def test_returns_false_promptly_when_stopped_while_waiting() -> None:
    stop = asyncio.Event()
    script = Script([BEHIND] * 10)

    async def wait_then_stop(event: asyncio.Event, seconds: float) -> None:
        await script.wait(event, seconds)
        stop.set()

    assert await wait_for_schema(script.check, stop, wait_then_stop) is False
    assert script.waits == [1]


async def test_returns_false_without_checking_when_already_stopped() -> None:
    stop = asyncio.Event()
    stop.set()
    script = Script([READY])
    assert await wait_for_schema(script.check, stop, script.wait) is False
    assert script.waits == []


@pytest.mark.parametrize(
    "error",
    [
        OperationalError("SELECT 1", {}, Exception("down")),
        SQLAlchemyError("boom"),
        OSError("unreachable"),
        TimeoutError("timed out"),
    ],
    ids=["OperationalError", "SQLAlchemyError", "OSError", "TimeoutError"],
)
async def test_connectivity_errors_count_as_not_ready_and_warn(
    error: BaseException, caplog: pytest.LogCaptureFixture
) -> None:
    script = Script([error, error, READY])
    with caplog.at_level(logging.WARNING):
        assert await wait_for_schema(script.check, asyncio.Event(), script.wait) is True
    assert script.waits == [1, 2]
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 2
    assert all("database unavailable" in message for message in warnings)


async def test_alembic_configuration_errors_are_not_retried() -> None:
    script = Script([CommandError("Multiple head revisions are present"), READY])
    with pytest.raises(SchemaCheckError, match="Multiple head revisions"):
        await wait_for_schema(script.check, asyncio.Event(), script.wait)
    assert script.waits == []
    assert len(script.results) == 1


async def test_unknown_revision_fails_fast_with_a_clear_message() -> None:
    script = Script([UNKNOWN, READY])
    with pytest.raises(SchemaCheckError, match="does not know"):
        await wait_for_schema(script.check, asyncio.Event(), script.wait)
    assert script.waits == []


async def test_missing_alembic_script_directory_raises_command_error(tmp_path: Path) -> None:
    config = alembic_config(ini_path=tmp_path / "alembic.ini")
    engine = create_async_engine("postgresql+asyncpg://u:p@127.0.0.1:1/none")
    try:
        with pytest.raises(CommandError):
            await schema_state(engine, config)
    finally:
        await engine.dispose()


def test_alembic_config_honors_a_custom_ini_path(tmp_path: Path) -> None:
    ini = tmp_path / "alembic.ini"
    ini.write_text("[alembic]\nscript_location = scripts\n")
    config = alembic_config(ini_path=ini)
    assert config.get_main_option("script_location") == str(tmp_path / "scripts")


def _script() -> ScriptDirectory:
    return ScriptDirectory.from_config(alembic_config())


def test_classify_revision_states() -> None:
    script = _script()
    head = script.get_current_head()
    assert head is not None
    assert classify_revision(script, head) is READY
    assert classify_revision(script, None) is BEHIND
    base = next(r for r in script.walk_revisions() if r.down_revision is None)
    if base.revision != head:
        assert classify_revision(script, base.revision) is BEHIND


def test_classify_revision_unknown_when_database_is_ahead_or_diverged() -> None:
    assert classify_revision(_script(), "ffffffffffff") is UNKNOWN


@pytest.mark.integration
async def test_schema_state_follows_migrations(migrated_database_url: str) -> None:
    config = alembic_config(migrated_database_url)
    engine = create_async_engine(migrated_database_url)
    try:
        assert await schema_state(engine, config) is READY
        await asyncio.to_thread(command.downgrade, config, "base")
        assert await schema_state(engine, config) is BEHIND
        await asyncio.to_thread(command.upgrade, config, "head")
        assert await schema_state(engine, config) is READY
    finally:
        # Leave the shared session database migrated for the other tests.
        await asyncio.to_thread(command.upgrade, config, "head")
        await engine.dispose()
