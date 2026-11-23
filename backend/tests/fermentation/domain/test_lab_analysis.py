from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest

from fermon.fermentation.domain import (
    Batch,
    BatchStatus,
    InvalidBatchTransitionError,
    InvalidLabAnalysisError,
    LabAnalysis,
    LabResult,
    QualityParameter,
    QualityProfile,
    QualitySpec,
    QualityStage,
    QualityStatus,
    SpecRange,
    StyleTemplate,
    TargetRanges,
    record_lab_analysis,
)

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
LATER = T0 + timedelta(hours=2)
PROFILE_ID = UUID(int=500)
OE = QualityParameter.ORIGINAL_EXTRACT
PH = QualityParameter.PH
BREWHOUSE = QualityStage.BREWHOUSE

PROFILE = QualityProfile(
    id=PROFILE_ID,
    name="Pale lager",
    created_at=T0,
    specs=(
        QualitySpec(BREWHOUSE, OE, SpecRange(9.9, 10.5), SpecRange(10.0, 10.4), 10.2),
        QualitySpec(BREWHOUSE, PH, SpecRange(5.0, 5.5)),
    ),
)


def make_batch(**overrides: Any) -> Batch:
    values: dict[str, Any] = {
        "id": UUID(int=1),
        "tank_id": "tank-1",
        "beer_name": "Pale Lager",
        "style": "Lager",
        "template": StyleTemplate.LAGER,
        "targets": TargetRanges(8.0, 12.0, 1.2),
        "status": BatchStatus.ACTIVE,
        "planned_start": T0,
        "started_at": T0,
        "created_at": T0,
        "quality_profile_id": PROFILE_ID,
    }
    return Batch(**{**values, **overrides})


def record(**overrides: Any) -> LabAnalysis:
    values: dict[str, Any] = {
        "id": UUID(int=9),
        "batch": make_batch(),
        "profile": PROFILE,
        "stage": BREWHOUSE,
        "values": {OE: 10.45, PH: 5.2},
        "sampled_at": T0,
        "created_at": LATER,
    }
    return record_lab_analysis(**{**values, **overrides})


def make_analysis(**overrides: Any) -> LabAnalysis:
    values: dict[str, Any] = {
        "id": UUID(int=9),
        "batch_id": UUID(int=1),
        "stage": BREWHOUSE,
        "sampled_at": T0,
        "created_at": LATER,
        "results": (LabResult(OE, 10.2, QualityStatus.IN_SPEC),),
    }
    return LabAnalysis(**{**values, **overrides})


# --- recording from a batch --------------------------------------------------------------------


def test_recording_evaluates_each_value_against_the_batch_profile() -> None:
    analysis = record()

    assert analysis.batch_id == UUID(int=1)
    assert analysis.quality_profile_id == PROFILE_ID
    assert analysis.results == (
        LabResult(OE, 10.45, QualityStatus.WARNING),
        LabResult(PH, 5.2, QualityStatus.IN_SPEC),
    )


def test_parameters_without_a_spec_at_that_stage_are_no_spec() -> None:
    analysis = record(stage=QualityStage.PACKAGED)

    assert {r.status for r in analysis.results} == {QualityStatus.NO_SPEC}


def test_a_batch_without_profile_records_every_value_as_no_spec() -> None:
    analysis = record(batch=make_batch(quality_profile_id=None), profile=None)

    assert analysis.quality_profile_id is None
    assert {r.status for r in analysis.results} == {QualityStatus.NO_SPEC}


def test_the_profile_must_be_the_batch_profile() -> None:
    with pytest.raises(InvalidLabAnalysisError) as error:
        record(batch=make_batch(quality_profile_id=None))
    assert error.value.field == "quality_profile_id"

    with pytest.raises(InvalidLabAnalysisError):
        record(profile=None)


def test_parameter_codes_are_accepted_as_keys() -> None:
    analysis = record(values={"ph": 5.2})

    assert analysis.results == (LabResult(PH, 5.2, QualityStatus.IN_SPEC),)


@pytest.mark.parametrize(
    ("values", "field"),
    [
        ({}, "values"),
        ({"gravity": 1.0}, "values.gravity"),
        ({PH: 15.0}, "values.ph"),
        ({OE: float("nan")}, "values.original_extract"),
    ],
)
def test_values_must_be_known_plausible_and_present(values: dict[Any, float], field: str) -> None:
    with pytest.raises(InvalidLabAnalysisError) as error:
        record(values=values)
    assert error.value.field == field


def test_a_planned_batch_cannot_have_analyses() -> None:
    planned = make_batch(status=BatchStatus.PLANNED, started_at=None)

    with pytest.raises(InvalidBatchTransitionError):
        record(batch=planned)


def test_a_finished_batch_can_still_be_analyzed() -> None:
    finished = make_batch(status=BatchStatus.FINISHED, finished_at=LATER)

    assert record(batch=finished, stage=QualityStage.PACKAGED).stage is QualityStage.PACKAGED


# --- the analysis record -----------------------------------------------------------------------


def test_results_are_ordered_by_the_parameter_catalog() -> None:
    analysis = make_analysis(
        results=(
            LabResult(PH, 5.2, QualityStatus.IN_SPEC),
            LabResult(OE, 10.2, QualityStatus.IN_SPEC),
        )
    )

    assert [r.parameter for r in analysis.results] == [OE, PH]


def test_a_parameter_appears_once() -> None:
    with pytest.raises(InvalidLabAnalysisError) as error:
        make_analysis(
            results=(
                LabResult(OE, 10.2, QualityStatus.IN_SPEC),
                LabResult(OE, 10.3, QualityStatus.IN_SPEC),
            )
        )
    assert error.value.field == "values"


def test_sampled_at_cannot_be_after_the_record() -> None:
    with pytest.raises(InvalidLabAnalysisError) as error:
        make_analysis(sampled_at=LATER + timedelta(seconds=1))
    assert error.value.field == "sampled_at"


def test_datetimes_must_be_timezone_aware() -> None:
    with pytest.raises(InvalidLabAnalysisError) as error:
        make_analysis(sampled_at=datetime(2026, 1, 1))  # noqa: DTZ001
    assert error.value.field == "sampled_at"


def test_analyst_and_notes_are_trimmed_and_blank_becomes_none() -> None:
    analysis = make_analysis(analyst="  M. Ruiz ", notes="   ")

    assert (analysis.analyst, analysis.notes) == ("M. Ruiz", None)


def test_result_status_and_parameter_are_parsed_from_codes() -> None:
    result = LabResult("ph", 5, "warning")  # type: ignore[arg-type]

    assert (result.parameter, result.value, result.status) == (PH, 5.0, QualityStatus.WARNING)
    assert isinstance(result.value, float)
