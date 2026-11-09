"""Composition of the reading ingest and alert use cases, shared by the ingestor and the API.

Both entry points must evaluate alerts the same way after a reading is stored, so the wiring
lives here once instead of being repeated in each process.
"""

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fermon.fermentation.application import (
    CheckSilentSensors,
    Clock,
    EvaluateReadingAlerts,
    FinishBatch,
    IngestReading,
    ResolveBatchAlerts,
    ResolveOrphanAlerts,
)
from fermon.fermentation.domain import AlertRules
from fermon.fermentation.infrastructure.persistence import (
    SqlAlchemyAlertRepository,
    SqlAlchemyBatchRepository,
    SqlAlchemyReadingRepository,
    SqlAlchemyTankRepository,
)
from fermon.shared.config import Settings

logger = logging.getLogger(__name__)


def alert_rules(settings: Settings) -> AlertRules:
    return AlertRules(
        out_of_range_after=timedelta(seconds=settings.alert_out_of_range_seconds),
        resolve_after=timedelta(seconds=settings.alert_resolve_seconds),
        silent_after=timedelta(seconds=settings.alert_silent_seconds),
    )


def build_ingest_reading(
    sessions: async_sessionmaker[AsyncSession], rules: AlertRules
) -> IngestReading:
    """``IngestReading`` that evaluates alerts after each newly stored reading."""
    readings = SqlAlchemyReadingRepository(sessions)
    evaluate = EvaluateReadingAlerts(
        readings,
        SqlAlchemyBatchRepository(sessions),
        SqlAlchemyAlertRepository(sessions),
        rules,
    )
    return IngestReading(
        readings, SqlAlchemyTankRepository(sessions), after_created=evaluate.execute
    )


def build_finish_batch(sessions: async_sessionmaker[AsyncSession], clock: Clock) -> FinishBatch:
    """``FinishBatch`` that resolves the finished batch's alerts."""
    return FinishBatch(
        SqlAlchemyBatchRepository(sessions),
        clock,
        after_finished=ResolveBatchAlerts(SqlAlchemyAlertRepository(sessions)).execute,
    )


def build_check_silent_sensors(
    sessions: async_sessionmaker[AsyncSession], rules: AlertRules
) -> CheckSilentSensors:
    return CheckSilentSensors(
        SqlAlchemyReadingRepository(sessions),
        SqlAlchemyBatchRepository(sessions),
        SqlAlchemyAlertRepository(sessions),
        rules,
        clock=lambda: datetime.now(UTC),
    )


def build_alert_maintenance(
    sessions: async_sessionmaker[AsyncSession], rules: AlertRules
) -> Callable[[], Awaitable[None]]:
    """One periodic tick: resolve orphaned alerts, then check for silent sensors.

    The two steps are independent, so a failing sweep is logged and never skips the silent check.
    """
    orphans = ResolveOrphanAlerts(
        SqlAlchemyBatchRepository(sessions),
        SqlAlchemyAlertRepository(sessions),
        clock=lambda: datetime.now(UTC),
    )
    silent = build_check_silent_sensors(sessions, rules)

    async def tick() -> None:
        try:
            await orphans.execute()
        except Exception:
            logger.error("orphan alert sweep failed", exc_info=True)
        await silent.execute()

    return tick
