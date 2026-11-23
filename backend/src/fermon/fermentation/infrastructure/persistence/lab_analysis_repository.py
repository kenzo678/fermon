from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fermon.fermentation.domain import BatchNotFoundError, LabAnalysis, LabResult, QualityStage
from fermon.fermentation.infrastructure.persistence.tables import lab_analyses, lab_results

BATCH_FOREIGN_KEY = "fk_lab_analyses_batch_id"


class SqlAlchemyLabAnalysisRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def add(self, analysis: LabAnalysis) -> None:
        try:
            async with self._session_factory() as session, session.begin():
                await session.execute(
                    lab_analyses.insert().values(
                        id=analysis.id,
                        batch_id=analysis.batch_id,
                        stage=analysis.stage.value,
                        sampled_at=analysis.sampled_at,
                        created_at=analysis.created_at,
                        analyst=analysis.analyst,
                        notes=analysis.notes,
                        quality_profile_id=analysis.quality_profile_id,
                    )
                )
                await session.execute(
                    lab_results.insert(),
                    [
                        {
                            "analysis_id": analysis.id,
                            "parameter": result.parameter.value,
                            "value": result.value,
                            "status": result.status.value,
                        }
                        for result in analysis.results
                    ],
                )
        except IntegrityError as error:
            if BATCH_FOREIGN_KEY in str(error.orig):
                raise BatchNotFoundError(str(analysis.batch_id)) from None
            raise

    async def get(self, analysis_id: UUID) -> LabAnalysis | None:
        found = await self._load(select(lab_analyses).where(lab_analyses.c.id == analysis_id))
        return found[0] if found else None

    async def list_for_batch(
        self, batch_id: UUID, stage: QualityStage | None = None
    ) -> list[LabAnalysis]:
        statement = (
            select(lab_analyses)
            .where(lab_analyses.c.batch_id == batch_id)
            .order_by(lab_analyses.c.sampled_at, lab_analyses.c.created_at, lab_analyses.c.id)
        )
        if stage is not None:
            statement = statement.where(lab_analyses.c.stage == stage.value)
        return await self._load(statement)

    async def _load(self, statement: Any) -> list[LabAnalysis]:
        """The analyses selected by ``statement`` (in its order), each with its results."""
        async with self._session_factory() as session:
            rows = (await session.execute(statement)).all()
            ids = [row.id for row in rows]
            result_rows = (
                (
                    await session.execute(
                        select(lab_results).where(lab_results.c.analysis_id.in_(ids))
                    )
                ).all()
                if ids
                else []
            )
        results: dict[UUID, list[LabResult]] = {analysis_id: [] for analysis_id in ids}
        for row in result_rows:
            results[row.analysis_id].append(LabResult(row.parameter, row.value, row.status))
        return [_to_domain(row, results[row.id]) for row in rows]


def _to_domain(row: Any, results: list[LabResult]) -> LabAnalysis:
    return LabAnalysis(
        id=row.id,
        batch_id=row.batch_id,
        stage=row.stage,
        sampled_at=row.sampled_at,
        created_at=row.created_at,
        results=tuple(results),
        analyst=row.analyst,
        notes=row.notes,
        quality_profile_id=row.quality_profile_id,
    )
