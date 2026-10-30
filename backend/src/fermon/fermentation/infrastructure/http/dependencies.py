from typing import Annotated

from fastapi import Depends
from fastapi.requests import HTTPConnection
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fermon.fermentation.application.get_tank import GetTank
from fermon.fermentation.application.ingest_reading import IngestReading
from fermon.fermentation.application.list_aggregated_readings import ListAggregatedReadings
from fermon.fermentation.application.list_readings import ListReadings
from fermon.fermentation.application.list_tanks import ListTanks
from fermon.fermentation.infrastructure.persistence import (
    SqlAlchemyReadingRepository,
    SqlAlchemyTankRepository,
)
from fermon.fermentation.infrastructure.realtime import ReadingFeed


def get_session_factory(connection: HTTPConnection) -> async_sessionmaker[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] = connection.app.state.session_factory
    return factory


def get_reading_feed(connection: HTTPConnection) -> ReadingFeed:
    feed: ReadingFeed = connection.app.state.reading_feed
    return feed


SessionFactory = Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)]


def get_ingest_reading(session_factory: SessionFactory) -> IngestReading:
    return IngestReading(
        SqlAlchemyReadingRepository(session_factory), SqlAlchemyTankRepository(session_factory)
    )


def get_list_readings(session_factory: SessionFactory) -> ListReadings:
    return ListReadings(SqlAlchemyReadingRepository(session_factory))


def get_list_tanks(session_factory: SessionFactory) -> ListTanks:
    return ListTanks(
        SqlAlchemyTankRepository(session_factory), SqlAlchemyReadingRepository(session_factory)
    )


def get_get_tank(session_factory: SessionFactory) -> GetTank:
    return GetTank(
        SqlAlchemyTankRepository(session_factory), SqlAlchemyReadingRepository(session_factory)
    )


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
