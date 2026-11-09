from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends
from fastapi.requests import HTTPConnection
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fermon.fermentation.application.batches import (
    Clock,
    CreateBatch,
    FinishBatch,
    GetBatch,
    ListBatches,
    StartBatch,
    UpdateBatch,
)
from fermon.fermentation.application.get_tank import GetTank
from fermon.fermentation.application.ingest_reading import IngestReading
from fermon.fermentation.application.list_aggregated_readings import ListAggregatedReadings
from fermon.fermentation.application.list_readings import ListReadings
from fermon.fermentation.application.list_tanks import ListTanks
from fermon.fermentation.domain import AlertRules
from fermon.fermentation.infrastructure.persistence import (
    SqlAlchemyBatchRepository,
    SqlAlchemyReadingRepository,
    SqlAlchemyTankRepository,
)
from fermon.fermentation.infrastructure.realtime import ReadingFeed
from fermon.fermentation.infrastructure.wiring import build_finish_batch, build_ingest_reading


def get_session_factory(connection: HTTPConnection) -> async_sessionmaker[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] = connection.app.state.session_factory
    return factory


def get_reading_feed(connection: HTTPConnection) -> ReadingFeed:
    feed: ReadingFeed = connection.app.state.reading_feed
    return feed


SessionFactory = Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)]


def get_alert_rules(connection: HTTPConnection) -> AlertRules:
    rules: AlertRules = connection.app.state.alert_rules
    return rules


AlertRulesDep = Annotated[AlertRules, Depends(get_alert_rules)]


def get_ingest_reading(session_factory: SessionFactory, rules: AlertRulesDep) -> IngestReading:
    return build_ingest_reading(session_factory, rules)


def get_list_readings(session_factory: SessionFactory) -> ListReadings:
    return ListReadings(SqlAlchemyReadingRepository(session_factory))


def get_list_tanks(session_factory: SessionFactory) -> ListTanks:
    return ListTanks(
        SqlAlchemyTankRepository(session_factory),
        SqlAlchemyReadingRepository(session_factory),
        SqlAlchemyBatchRepository(session_factory),
    )


def get_get_tank(session_factory: SessionFactory) -> GetTank:
    return GetTank(
        SqlAlchemyTankRepository(session_factory),
        SqlAlchemyReadingRepository(session_factory),
        SqlAlchemyBatchRepository(session_factory),
    )


def get_clock() -> Clock:
    return lambda: datetime.now(UTC)


ClockDep = Annotated[Clock, Depends(get_clock)]


def get_create_batch(session_factory: SessionFactory, clock: ClockDep) -> CreateBatch:
    return CreateBatch(
        SqlAlchemyBatchRepository(session_factory), SqlAlchemyTankRepository(session_factory), clock
    )


def get_update_batch(session_factory: SessionFactory) -> UpdateBatch:
    return UpdateBatch(SqlAlchemyBatchRepository(session_factory))


def get_start_batch(session_factory: SessionFactory, clock: ClockDep) -> StartBatch:
    return StartBatch(SqlAlchemyBatchRepository(session_factory), clock)


def get_finish_batch(session_factory: SessionFactory, clock: ClockDep) -> FinishBatch:
    return build_finish_batch(session_factory, clock)


def get_get_batch(session_factory: SessionFactory) -> GetBatch:
    return GetBatch(SqlAlchemyBatchRepository(session_factory))


def get_list_batches(session_factory: SessionFactory) -> ListBatches:
    return ListBatches(SqlAlchemyBatchRepository(session_factory))


def get_list_aggregated_readings(session_factory: SessionFactory) -> ListAggregatedReadings:
    return ListAggregatedReadings(
        SqlAlchemyTankRepository(session_factory), SqlAlchemyReadingRepository(session_factory)
    )


IngestReadingDep = Annotated[IngestReading, Depends(get_ingest_reading)]
ListReadingsDep = Annotated[ListReadings, Depends(get_list_readings)]
ListTanksDep = Annotated[ListTanks, Depends(get_list_tanks)]
GetTankDep = Annotated[GetTank, Depends(get_get_tank)]
ReadingFeedDep = Annotated[ReadingFeed, Depends(get_reading_feed)]
ListAggregatedReadingsDep = Annotated[ListAggregatedReadings, Depends(get_list_aggregated_readings)]
CreateBatchDep = Annotated[CreateBatch, Depends(get_create_batch)]
UpdateBatchDep = Annotated[UpdateBatch, Depends(get_update_batch)]
StartBatchDep = Annotated[StartBatch, Depends(get_start_batch)]
FinishBatchDep = Annotated[FinishBatch, Depends(get_finish_batch)]
GetBatchDep = Annotated[GetBatch, Depends(get_get_batch)]
ListBatchesDep = Annotated[ListBatches, Depends(get_list_batches)]
