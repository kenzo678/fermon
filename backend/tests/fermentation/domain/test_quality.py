import math
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest

from fermon.fermentation.domain import (
    InvalidQualityError,
    QualityParameter,
    QualityProfile,
    QualitySpec,
    QualitySpecNotFoundError,
    QualityStage,
    QualityStatus,
    SpecRange,
)

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
OE = QualityParameter.ORIGINAL_EXTRACT
PH = QualityParameter.PH


def oe_spec(**overrides: Any) -> QualitySpec:
    values: dict[str, Any] = {
        "stage": QualityStage.BREWHOUSE,
        "parameter": OE,
        "acceptance": SpecRange(9.9, 10.5),
        "internal": SpecRange(10.0, 10.4),
        "target": 10.2,
    }
    return QualitySpec(**{**values, **overrides})


def profile(*specs: QualitySpec, **overrides: Any) -> QualityProfile:
    values: dict[str, Any] = {"id": UUID(int=1), "name": "Pale lager", "created_at": T0}
    return QualityProfile(**{**values, **overrides}, specs=specs)


def field_of(error: pytest.ExceptionInfo[InvalidQualityError]) -> str:
    return error.value.field


# --- catalog -----------------------------------------------------------------------------------


def test_parameters_have_label_unit_and_plausible_limits() -> None:
    assert OE.value == "original_extract"
    assert OE.label == "Original extract"
    assert OE.unit == "°P"
    assert OE.limits == (0.0, 30.0)
    assert PH.limits == (0.0, 14.0)


def test_every_parameter_has_an_ordered_range() -> None:
    for parameter in QualityParameter:
        low, high = parameter.limits
        assert low < high, parameter
        assert parameter.unit, parameter
        assert parameter.label, parameter


def test_stages_are_the_four_lab_checkpoints() -> None:
    assert [s.value for s in QualityStage] == ["brewhouse", "maturation", "bright_beer", "packaged"]


# --- specification invariants ------------------------------------------------------------------


def test_a_full_two_tier_spec_is_valid() -> None:
    spec = oe_spec()
    assert spec.acceptance == SpecRange(9.9, 10.5)
    assert spec.internal == SpecRange(10.0, 10.4)
    assert spec.target == 10.2


def test_one_sided_limits_are_allowed() -> None:
    spec = oe_spec(
        parameter=QualityParameter.SULFUR_DIOXIDE,
        acceptance=SpecRange(maximum=12.0),
        internal=SpecRange(maximum=10.0),
        target=None,
    )
    assert spec.internal == SpecRange(None, 10.0)


def test_acceptance_needs_at_least_one_bound() -> None:
    with pytest.raises(InvalidQualityError) as error:
        oe_spec(acceptance=SpecRange(), internal=None, target=None)
    assert field_of(error) == "acceptance"


def test_range_minimum_must_be_lower_than_maximum() -> None:
    with pytest.raises(InvalidQualityError) as error:
        oe_spec(acceptance=SpecRange(10.5, 10.5), internal=None, target=None)
    assert field_of(error) == "acceptance.max"


@pytest.mark.parametrize("bad", [math.nan, math.inf, True, "10"])
def test_bounds_must_be_finite_real_numbers(bad: object) -> None:
    with pytest.raises(InvalidQualityError) as error:
        oe_spec(acceptance=SpecRange(bad, 10.5))  # type: ignore[arg-type]
    assert field_of(error) == "acceptance.min"


def test_bounds_must_be_physically_plausible_for_the_parameter() -> None:
    with pytest.raises(InvalidQualityError) as error:
        oe_spec(parameter=PH, acceptance=SpecRange(4.0, 40.0), internal=None, target=None)
    assert field_of(error) == "acceptance.max"


def test_integers_are_accepted_and_stored_as_floats() -> None:
    spec = oe_spec(acceptance=SpecRange(9, 11), internal=None, target=10)
    assert spec.acceptance == SpecRange(9.0, 11.0)
    assert isinstance(spec.acceptance.minimum, float)
    assert isinstance(spec.target, float)


@pytest.mark.parametrize(
    ("internal", "field"),
    [
        (SpecRange(9.8, 10.4), "internal.min"),
        (SpecRange(10.0, 10.6), "internal.max"),
        (SpecRange(maximum=10.4), "internal.min"),  # open below while acceptance is closed
        (SpecRange(minimum=10.0), "internal.max"),
    ],
)
def test_internal_range_must_lie_inside_acceptance(internal: SpecRange, field: str) -> None:
    with pytest.raises(InvalidQualityError) as error:
        oe_spec(internal=internal, target=None)
    assert field_of(error) == field


def test_internal_range_may_touch_the_acceptance_bounds() -> None:
    assert oe_spec(internal=SpecRange(9.9, 10.5)).internal == SpecRange(9.9, 10.5)


@pytest.mark.parametrize(("internal", "target"), [(SpecRange(10.0, 10.4), 10.45), (None, 10.6)])
def test_target_must_lie_inside_the_tightest_range(
    internal: SpecRange | None, target: float
) -> None:
    with pytest.raises(InvalidQualityError) as error:
        oe_spec(internal=internal, target=target)
    assert field_of(error) == "target"


def test_stage_and_parameter_are_parsed_from_their_codes() -> None:
    spec = oe_spec(stage="maturation", parameter="ph", acceptance=SpecRange(4.1, 4.7),
                   internal=None, target=None)  # fmt: skip
    assert spec.stage is QualityStage.MATURATION
    assert spec.parameter is PH


@pytest.mark.parametrize(("field", "value"), [("stage", "mash"), ("parameter", "gravity")])
def test_unknown_stage_or_parameter_is_rejected(field: str, value: str) -> None:
    with pytest.raises(InvalidQualityError) as error:
        oe_spec(**{field: value})
    assert field_of(error) == field


# --- evaluation --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "status"),
    [
        (10.2, QualityStatus.IN_SPEC),
        (10.0, QualityStatus.IN_SPEC),  # bounds are inclusive
        (10.4, QualityStatus.IN_SPEC),
        (10.45, QualityStatus.WARNING),
        (9.9, QualityStatus.WARNING),
        (10.5, QualityStatus.WARNING),
        (10.51, QualityStatus.OUT_OF_SPEC),
        (9.0, QualityStatus.OUT_OF_SPEC),
    ],
)
def test_evaluate_uses_both_tiers(value: float, status: QualityStatus) -> None:
    assert oe_spec().evaluate(value) is status


def test_without_internal_range_acceptance_is_the_only_tier() -> None:
    spec = oe_spec(internal=None, target=None)
    assert spec.evaluate(9.95) is QualityStatus.IN_SPEC
    assert spec.evaluate(10.6) is QualityStatus.OUT_OF_SPEC


def test_one_sided_evaluation() -> None:
    spec = oe_spec(
        parameter=QualityParameter.DIACETYL,
        acceptance=SpecRange(maximum=50.0),
        internal=SpecRange(maximum=40.0),
        target=None,
    )
    assert spec.evaluate(0.0) is QualityStatus.IN_SPEC
    assert spec.evaluate(45.0) is QualityStatus.WARNING
    assert spec.evaluate(51.0) is QualityStatus.OUT_OF_SPEC


@pytest.mark.parametrize("bad", [math.nan, 31.0, -0.1, "10"])
def test_evaluated_values_must_be_plausible(bad: object) -> None:
    with pytest.raises(InvalidQualityError) as error:
        oe_spec().evaluate(bad)  # type: ignore[arg-type]
    assert field_of(error) == "original_extract"


# --- profiles ----------------------------------------------------------------------------------


def test_profile_name_is_trimmed_and_required() -> None:
    assert profile(name="  Pale lager ").name == "Pale lager"
    with pytest.raises(InvalidQualityError) as error:
        profile(name="   ")
    assert field_of(error) == "name"


def test_blank_description_becomes_none() -> None:
    assert profile(description="  ").description is None
    assert profile(description=" crisp ").description == "crisp"


def test_created_at_must_be_timezone_aware() -> None:
    with pytest.raises(InvalidQualityError) as error:
        profile(created_at=datetime(2026, 1, 1))  # noqa: DTZ001
    assert field_of(error) == "created_at"


def test_at_most_one_spec_per_stage_and_parameter() -> None:
    with pytest.raises(InvalidQualityError) as error:
        profile(oe_spec(), oe_spec(target=None))
    assert field_of(error) == "specs"


def test_specs_are_ordered_by_stage_then_parameter() -> None:
    packaged_ph = oe_spec(stage=QualityStage.PACKAGED, parameter=PH,
                          acceptance=SpecRange(4.1, 4.7), internal=None, target=None)  # fmt: skip
    brewhouse_ph = oe_spec(parameter=PH, acceptance=SpecRange(5.0, 5.4), internal=None,
                           target=None)  # fmt: skip
    ordered = profile(packaged_ph, oe_spec(), brewhouse_ph).specs
    assert [(s.stage, s.parameter) for s in ordered] == [
        (QualityStage.BREWHOUSE, OE),
        (QualityStage.BREWHOUSE, PH),
        (QualityStage.PACKAGED, PH),
    ]


def test_with_spec_adds_or_replaces() -> None:
    replaced = profile(oe_spec()).with_spec(oe_spec(target=None))
    assert len(replaced.specs) == 1
    assert replaced.spec_for(QualityStage.BREWHOUSE, OE) == oe_spec(target=None)


def test_without_spec_removes_or_raises() -> None:
    assert profile(oe_spec()).without_spec(QualityStage.BREWHOUSE, OE).specs == ()
    with pytest.raises(QualitySpecNotFoundError):
        profile().without_spec(QualityStage.BREWHOUSE, OE)


def test_profile_evaluates_one_stage_and_marks_unspecified_parameters() -> None:
    result = profile(oe_spec()).evaluate(QualityStage.BREWHOUSE, {OE: 10.45, PH: 5.2})
    assert result == {OE: QualityStatus.WARNING, PH: QualityStatus.NO_SPEC}


def test_profile_evaluation_ignores_specs_of_other_stages() -> None:
    result = profile(oe_spec()).evaluate(QualityStage.PACKAGED, {OE: 10.2})
    assert result == {OE: QualityStatus.NO_SPEC}


def test_unspecified_values_must_still_be_plausible() -> None:
    with pytest.raises(InvalidQualityError) as error:
        profile().evaluate(QualityStage.BREWHOUSE, {PH: 15.0})
    assert field_of(error) == "ph"
