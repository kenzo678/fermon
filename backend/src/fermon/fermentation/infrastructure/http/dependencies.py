from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fermon.fermentation.application.ingest_reading import IngestReading
from fermon.fermentation.application.list_readings import ListReadings
from fermon.fermentation.infrastructure.persistence import SqlAlchemyReadingRepository


def get_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    return factory


SessionFactory = Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)]


def get_ingest_reading(session_factory: SessionFactory) -> IngestReading:
    return IngestReading(SqlAlchemyReadingRepository(session_factory))


def get_list_readings(session_factory: SessionFactory) -> ListReadings:
    return ListReadings(SqlAlchemyReadingRepository(session_factory))


IngestReadingDep = Annotated[IngestReading, Depends(get_ingest_reading)]
ListReadingsDep = Annotated[ListReadings, Depends(get_list_readings)]
