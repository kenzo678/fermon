from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends
from fastapi.requests import HTTPConnection
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fermon.fermentation.application.batch_report import BuildBatchReport
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
from fermon.fermentation.application.lab_analyses import (
    GetLabAnalysis,
    ListLabAnalyses,
    RecordLabAnalysis,
)
from fermon.fermentation.application.list_aggregated_readings import ListAggregatedReadings
from fermon.fermentation.application.list_readings import ListReadings
from fermon.fermentation.application.list_tanks import ListTanks
from fermon.fermentation.application.manage_alerts import AcknowledgeAlert, GetAlert, ListAlerts
from fermon.fermentation.application.quality import (
    CreateQualityProfile,
    EvaluateQualityValues,
    GetQualityProfile,
    ListQualityProfiles,
    RemoveQualitySpec,
    SaveQualitySpec,
)
from fermon.fermentation.application.rename_tank import RenameTank
from fermon.fermentation.domain import AlertRules
from fermon.fermentation.infrastructure.persistence import (
    SqlAlchemyAlertRepository,
    SqlAlchemyBatchRepository,
    SqlAlchemyLabAnalysisRepository,
    SqlAlchemyQualityProfileRepository,
    SqlAlchemyReadingRepository,
    SqlAlchemyTankRepository,
)
from fermon.fermentation.infrastructure.realtime import AlertFeed, ReadingFeed
from fermon.fermentation.infrastructure.wiring import build_finish_batch, build_ingest_reading


def get_session_factory(connection: HTTPConnection) -> async_sessionmaker[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] = connection.app.state.session_factory
    return factory


def get_reading_feed(connection: HTTPConnection) -> ReadingFeed:
    feed: ReadingFeed = connection.app.state.reading_feed
    return feed


def get_alert_feed(connection: HTTPConnection) -> AlertFeed:
    feed: AlertFeed = connection.app.state.alert_feed
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
        SqlAlchemyAlertRepository(session_factory),
    )


def get_get_tank(session_factory: SessionFactory) -> GetTank:
    return GetTank(
        SqlAlchemyTankRepository(session_factory),
        SqlAlchemyReadingRepository(session_factory),
        SqlAlchemyBatchRepository(session_factory),
        SqlAlchemyAlertRepository(session_factory),
    )


def get_rename_tank(session_factory: SessionFactory) -> RenameTank:
    return RenameTank(SqlAlchemyTankRepository(session_factory), get_get_tank(session_factory))


def get_clock() -> Clock:
    return lambda: datetime.now(UTC)


ClockDep = Annotated[Clock, Depends(get_clock)]


def get_report_max_gap(connection: HTTPConnection) -> timedelta:
    gap: timedelta = connection.app.state.report_max_gap
    return gap


def get_build_batch_report(
    session_factory: SessionFactory,
    clock: ClockDep,
    max_gap: Annotated[timedelta, Depends(get_report_max_gap)],
) -> BuildBatchReport:
    return BuildBatchReport(
        SqlAlchemyBatchRepository(session_factory),
        SqlAlchemyReadingRepository(session_factory),
        SqlAlchemyAlertRepository(session_factory),
        SqlAlchemyLabAnalysisRepository(session_factory),
        SqlAlchemyQualityProfileRepository(session_factory),
        clock,
        max_gap,
    )


def get_create_batch(session_factory: SessionFactory, clock: ClockDep) -> CreateBatch:
    return CreateBatch(
        SqlAlchemyBatchRepository(session_factory),
        SqlAlchemyTankRepository(session_factory),
        SqlAlchemyQualityProfileRepository(session_factory),
        clock,
    )


def get_update_batch(session_factory: SessionFactory) -> UpdateBatch:
    return UpdateBatch(
        SqlAlchemyBatchRepository(session_factory),
        SqlAlchemyQualityProfileRepository(session_factory),
    )


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


def get_list_alerts(session_factory: SessionFactory) -> ListAlerts:
    return ListAlerts(SqlAlchemyAlertRepository(session_factory))


def get_get_alert(session_factory: SessionFactory) -> GetAlert:
    return GetAlert(SqlAlchemyAlertRepository(session_factory))


def get_acknowledge_alert(session_factory: SessionFactory, clock: ClockDep) -> AcknowledgeAlert:
    return AcknowledgeAlert(SqlAlchemyAlertRepository(session_factory), clock)


def get_record_lab_analysis(session_factory: SessionFactory, clock: ClockDep) -> RecordLabAnalysis:
    return RecordLabAnalysis(
        SqlAlchemyBatchRepository(session_factory),
        SqlAlchemyQualityProfileRepository(session_factory),
        SqlAlchemyLabAnalysisRepository(session_factory),
        clock,
    )


def get_list_lab_analyses(session_factory: SessionFactory) -> ListLabAnalyses:
    return ListLabAnalyses(
        SqlAlchemyBatchRepository(session_factory),
        SqlAlchemyLabAnalysisRepository(session_factory),
    )


def get_get_lab_analysis(session_factory: SessionFactory) -> GetLabAnalysis:
    return GetLabAnalysis(SqlAlchemyLabAnalysisRepository(session_factory))


def get_create_quality_profile(
    session_factory: SessionFactory, clock: ClockDep
) -> CreateQualityProfile:
    return CreateQualityProfile(SqlAlchemyQualityProfileRepository(session_factory), clock)


def get_list_quality_profiles(session_factory: SessionFactory) -> ListQualityProfiles:
    return ListQualityProfiles(SqlAlchemyQualityProfileRepository(session_factory))


def get_get_quality_profile(session_factory: SessionFactory) -> GetQualityProfile:
    return GetQualityProfile(SqlAlchemyQualityProfileRepository(session_factory))


def get_save_quality_spec(session_factory: SessionFactory) -> SaveQualitySpec:
    return SaveQualitySpec(SqlAlchemyQualityProfileRepository(session_factory))


def get_remove_quality_spec(session_factory: SessionFactory) -> RemoveQualitySpec:
    return RemoveQualitySpec(SqlAlchemyQualityProfileRepository(session_factory))


def get_evaluate_quality_values(session_factory: SessionFactory) -> EvaluateQualityValues:
    return EvaluateQualityValues(SqlAlchemyQualityProfileRepository(session_factory))


IngestReadingDep = Annotated[IngestReading, Depends(get_ingest_reading)]
ListReadingsDep = Annotated[ListReadings, Depends(get_list_readings)]
ListTanksDep = Annotated[ListTanks, Depends(get_list_tanks)]
GetTankDep = Annotated[GetTank, Depends(get_get_tank)]
RenameTankDep = Annotated[RenameTank, Depends(get_rename_tank)]
ReadingFeedDep = Annotated[ReadingFeed, Depends(get_reading_feed)]
ListAggregatedReadingsDep = Annotated[ListAggregatedReadings, Depends(get_list_aggregated_readings)]
BuildBatchReportDep = Annotated[BuildBatchReport, Depends(get_build_batch_report)]
CreateBatchDep = Annotated[CreateBatch, Depends(get_create_batch)]
UpdateBatchDep = Annotated[UpdateBatch, Depends(get_update_batch)]
StartBatchDep = Annotated[StartBatch, Depends(get_start_batch)]
FinishBatchDep = Annotated[FinishBatch, Depends(get_finish_batch)]
GetBatchDep = Annotated[GetBatch, Depends(get_get_batch)]
ListBatchesDep = Annotated[ListBatches, Depends(get_list_batches)]
ListAlertsDep = Annotated[ListAlerts, Depends(get_list_alerts)]
GetAlertDep = Annotated[GetAlert, Depends(get_get_alert)]
AcknowledgeAlertDep = Annotated[AcknowledgeAlert, Depends(get_acknowledge_alert)]
AlertFeedDep = Annotated[AlertFeed, Depends(get_alert_feed)]
CreateQualityProfileDep = Annotated[CreateQualityProfile, Depends(get_create_quality_profile)]
ListQualityProfilesDep = Annotated[ListQualityProfiles, Depends(get_list_quality_profiles)]
GetQualityProfileDep = Annotated[GetQualityProfile, Depends(get_get_quality_profile)]
SaveQualitySpecDep = Annotated[SaveQualitySpec, Depends(get_save_quality_spec)]
RemoveQualitySpecDep = Annotated[RemoveQualitySpec, Depends(get_remove_quality_spec)]
EvaluateQualityValuesDep = Annotated[EvaluateQualityValues, Depends(get_evaluate_quality_values)]
RecordLabAnalysisDep = Annotated[RecordLabAnalysis, Depends(get_record_lab_analysis)]
ListLabAnalysesDep = Annotated[ListLabAnalyses, Depends(get_list_lab_analyses)]
GetLabAnalysisDep = Annotated[GetLabAnalysis, Depends(get_get_lab_analysis)]
