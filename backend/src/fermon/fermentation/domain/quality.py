"""Laboratory quality specifications: two-tier ranges per process stage and parameter."""

import math
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from fermon.fermentation.domain.errors import (
    InvalidIdentifierError,
    InvalidQualityError,
    QualitySpecNotFoundError,
)
from fermon.fermentation.domain.identifier import normalize_id


class QualityStage(StrEnum):
    """Lab checkpoints of the brewing process, in process order."""

    BREWHOUSE = "brewhouse"  # cold wort after the fermentation tank is filled
    MATURATION = "maturation"  # end of the cold rest, before filtration
    BRIGHT_BEER = "bright_beer"  # filtered beer released from a bright-beer (pressure) tank
    PACKAGED = "packaged"  # finished product


class QualityStatus(StrEnum):
    IN_SPEC = "in_spec"  # inside the internal (operating) range
    WARNING = "warning"  # outside the internal range but inside the acceptance limit
    OUT_OF_SPEC = "out_of_spec"
    NO_SPEC = "no_spec"  # the profile does not specify this parameter at this stage


class QualityParameter(StrEnum):
    ORIGINAL_EXTRACT = "original_extract"
    APPARENT_EXTRACT = "apparent_extract"
    REAL_EXTRACT = "real_extract"
    ALCOHOL_BY_WEIGHT = "alcohol_by_weight"
    ALCOHOL_BY_VOLUME = "alcohol_by_volume"
    ATTENUATION = "attenuation"
    PH = "ph"
    COLOR = "color"
    BITTERNESS = "bitterness"
    TURBIDITY_90 = "turbidity_90"
    TURBIDITY_25 = "turbidity_25"
    WORT_OXYGEN = "wort_oxygen"
    FREE_AMINO_NITROGEN = "free_amino_nitrogen"
    CALCIUM = "calcium"
    SULFUR_DIOXIDE = "sulfur_dioxide"
    DISSOLVED_OXYGEN = "dissolved_oxygen"
    TOTAL_PACKAGE_OXYGEN = "total_package_oxygen"
    CARBON_DIOXIDE = "carbon_dioxide"
    FOAM_STABILITY = "foam_stability"
    DIACETYL = "diacetyl"
    PASTEURIZATION_UNITS = "pasteurization_units"
    TEMPERATURE = "temperature"

    @property
    def label(self) -> str:
        return _CATALOG[self][0]

    @property
    def unit(self) -> str:
        return _CATALOG[self][1]

    @property
    def limits(self) -> tuple[float, float]:
        """Inclusive physically plausible range (low, high) in the parameter's unit."""
        return _CATALOG[self][2]


_CATALOG: dict[QualityParameter, tuple[str, str, tuple[float, float]]] = {
    QualityParameter.ORIGINAL_EXTRACT: ("Original extract", "°P", (0.0, 30.0)),
    # A highly attenuated beer can read slightly below 0 °P on a hydrometer.
    QualityParameter.APPARENT_EXTRACT: ("Apparent extract", "°P", (-5.0, 30.0)),
    QualityParameter.REAL_EXTRACT: ("Real extract", "°P", (0.0, 30.0)),
    QualityParameter.ALCOHOL_BY_WEIGHT: ("Alcohol by weight", "% w/w", (0.0, 20.0)),
    QualityParameter.ALCOHOL_BY_VOLUME: ("Alcohol by volume", "% v/v", (0.0, 20.0)),
    # Apparent attenuation exceeds 100 % when the apparent extract is negative.
    QualityParameter.ATTENUATION: ("Apparent attenuation", "%", (0.0, 120.0)),
    QualityParameter.PH: ("pH", "pH", (0.0, 14.0)),
    QualityParameter.COLOR: ("Color", "EBC", (0.0, 300.0)),
    QualityParameter.BITTERNESS: ("Bitterness", "IBU", (0.0, 150.0)),
    QualityParameter.TURBIDITY_90: ("Turbidity 90°", "EBC", (0.0, 100.0)),
    QualityParameter.TURBIDITY_25: ("Turbidity 25°", "EBC", (0.0, 100.0)),
    QualityParameter.WORT_OXYGEN: ("Wort oxygen", "ppm", (0.0, 50.0)),
    QualityParameter.FREE_AMINO_NITROGEN: ("Free amino nitrogen", "ppm", (0.0, 1000.0)),
    QualityParameter.CALCIUM: ("Calcium", "ppm", (0.0, 1000.0)),
    QualityParameter.SULFUR_DIOXIDE: ("Sulfur dioxide", "ppm", (0.0, 100.0)),
    QualityParameter.DISSOLVED_OXYGEN: ("Dissolved oxygen", "ppb", (0.0, 10000.0)),
    QualityParameter.TOTAL_PACKAGE_OXYGEN: ("Total package oxygen", "ppb", (0.0, 10000.0)),
    QualityParameter.CARBON_DIOXIDE: ("Carbon dioxide", "g/L", (0.0, 15.0)),
    QualityParameter.FOAM_STABILITY: ("Foam stability", "s", (0.0, 1000.0)),
    QualityParameter.DIACETYL: ("Diacetyl", "ppb", (0.0, 5000.0)),
    QualityParameter.PASTEURIZATION_UNITS: ("Pasteurization units", "PU", (0.0, 200.0)),
    QualityParameter.TEMPERATURE: ("Temperature", "°C", (-20.0, 100.0)),
}


def check_value(parameter: QualityParameter, value: object, field: str | None = None) -> float:
    """``value`` as a float if it is a finite real number inside the parameter's limits."""
    field = field or parameter.value
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise InvalidQualityError(field, "must be a real number")
    if not math.isfinite(value):
        raise InvalidQualityError(field, "must be a finite number")
    low, high = parameter.limits
    if not low <= value <= high:
        raise InvalidQualityError(field, f"{value} is outside {low}..{high} {parameter.unit}")
    return float(value)


@dataclass(frozen=True, slots=True)
class SpecRange:
    """Inclusive range; an absent bound means "no limit on that side".

    ``<`` and ``≤`` limits are both stored as inclusive bounds: the difference is below the
    resolution of the lab instruments.
    """

    minimum: float | None = None
    maximum: float | None = None

    def contains(self, value: float) -> bool:
        above = self.minimum is None or value >= self.minimum
        below = self.maximum is None or value <= self.maximum
        return above and below


def _checked_range(field: str, parameter: QualityParameter, spec_range: object) -> SpecRange:
    if not isinstance(spec_range, SpecRange):
        raise InvalidQualityError(field, "must be a SpecRange")
    if spec_range.minimum is None and spec_range.maximum is None:
        raise InvalidQualityError(field, "needs at least one of min and max")
    low = (
        None
        if spec_range.minimum is None
        else check_value(parameter, spec_range.minimum, f"{field}.min")
    )
    high = (
        None
        if spec_range.maximum is None
        else check_value(parameter, spec_range.maximum, f"{field}.max")
    )
    if low is not None and high is not None and low >= high:
        raise InvalidQualityError(f"{field}.max", "must be greater than min")
    return SpecRange(low, high)


def _require_inside(inner: SpecRange, outer: SpecRange) -> None:
    # An open bound of the internal range is wider than any closed bound of the acceptance one.
    if outer.minimum is not None and (inner.minimum is None or inner.minimum < outer.minimum):
        raise InvalidQualityError("internal.min", "must lie inside the acceptance range")
    if outer.maximum is not None and (inner.maximum is None or inner.maximum > outer.maximum):
        raise InvalidQualityError("internal.max", "must lie inside the acceptance range")


def _enum[E: StrEnum](kind: type[E], field: str, value: object) -> E:
    if isinstance(value, str):
        try:
            return kind(value)
        except ValueError:
            pass
    choices = ", ".join(member.value for member in kind)
    raise InvalidQualityError(field, f"must be one of {choices}")


@dataclass(frozen=True, slots=True)
class QualitySpec:
    """What a lab value of one parameter must be at one stage: internal range inside acceptance."""

    stage: QualityStage
    parameter: QualityParameter
    acceptance: SpecRange
    internal: SpecRange | None = None
    target: float | None = None

    def __post_init__(self) -> None:
        stage = _enum(QualityStage, "stage", self.stage)
        parameter = _enum(QualityParameter, "parameter", self.parameter)
        acceptance = _checked_range("acceptance", parameter, self.acceptance)
        internal = (
            None if self.internal is None else _checked_range("internal", parameter, self.internal)
        )
        if internal is not None:
            _require_inside(internal, acceptance)
        target = None if self.target is None else check_value(parameter, self.target, "target")
        if target is not None and not (internal or acceptance).contains(target):
            raise InvalidQualityError("target", "must lie inside the internal range")
        object.__setattr__(self, "stage", stage)
        object.__setattr__(self, "parameter", parameter)
        object.__setattr__(self, "acceptance", acceptance)
        object.__setattr__(self, "internal", internal)
        object.__setattr__(self, "target", target)

    @property
    def key(self) -> tuple[QualityStage, QualityParameter]:
        return self.stage, self.parameter

    def evaluate(self, value: object) -> QualityStatus:
        checked = check_value(self.parameter, value)
        if (self.internal or self.acceptance).contains(checked):
            return QualityStatus.IN_SPEC
        if self.acceptance.contains(checked):
            return QualityStatus.WARNING
        return QualityStatus.OUT_OF_SPEC


_STAGE_ORDER = {stage: index for index, stage in enumerate(QualityStage)}


def _sort_key(spec: QualitySpec) -> tuple[int, str]:
    return _STAGE_ORDER[spec.stage], spec.parameter.value


@dataclass(frozen=True, slots=True)
class QualityProfile:
    """A named quality spec sheet (e.g. "Pale lager"): at most one spec per stage and parameter."""

    id: UUID
    name: str
    created_at: datetime
    description: str | None = None
    specs: tuple[QualitySpec, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID):
            raise InvalidQualityError("id", "must be a UUID")
        try:
            object.__setattr__(self, "name", normalize_id("name", self.name))
        except InvalidIdentifierError as error:
            raise InvalidQualityError(error.field, error.reason) from None
        if not isinstance(self.created_at, datetime) or self.created_at.utcoffset() is None:
            raise InvalidQualityError("created_at", "must be a timezone-aware datetime")
        if self.description is not None:
            if not isinstance(self.description, str):
                raise InvalidQualityError("description", "must be a string")
            object.__setattr__(self, "description", self.description.strip() or None)
        specs = tuple(self.specs)
        if len({spec.key for spec in specs}) != len(specs):
            raise InvalidQualityError("specs", "at most one specification per stage and parameter")
        object.__setattr__(self, "specs", tuple(sorted(specs, key=_sort_key)))

    def spec_for(self, stage: QualityStage, parameter: QualityParameter) -> QualitySpec | None:
        return next((s for s in self.specs if s.key == (stage, parameter)), None)

    def with_spec(self, spec: QualitySpec) -> "QualityProfile":
        """A copy where ``spec`` is added, replacing any spec of the same stage and parameter."""
        others = tuple(s for s in self.specs if s.key != spec.key)
        return replace(self, specs=(*others, spec))

    def without_spec(self, stage: QualityStage, parameter: QualityParameter) -> "QualityProfile":
        if self.spec_for(stage, parameter) is None:
            raise QualitySpecNotFoundError(stage.value, parameter.value)
        return replace(self, specs=tuple(s for s in self.specs if s.key != (stage, parameter)))

    def evaluate(
        self, stage: QualityStage, values: Mapping[QualityParameter, object]
    ) -> dict[QualityParameter, QualityStatus]:
        """The status of each value at ``stage``; NO_SPEC where the profile has no spec."""
        result: dict[QualityParameter, QualityStatus] = {}
        for parameter, value in values.items():
            spec = self.spec_for(stage, parameter)
            if spec is None:
                check_value(parameter, value)
                result[parameter] = QualityStatus.NO_SPEC
            else:
                result[parameter] = spec.evaluate(value)
        return result


class QualityTemplate(StrEnum):
    PALE_LAGER = "pale_lager"


Bounds = tuple[float | None, float | None]


def _spec(
    stage: QualityStage,
    parameter: QualityParameter,
    acceptance: Bounds,
    internal: Bounds | None = None,
    target: float | None = None,
) -> QualitySpec:
    return QualitySpec(
        stage,
        parameter,
        acceptance=SpecRange(*acceptance),
        internal=None if internal is None else SpecRange(*internal),
        target=target,
    )


_P = QualityParameter
_S = QualityStage

# Illustrative textbook values for a pale lager, meant as a starting point to edit: they are not
# the specifications of any real brewery or product.
_TEMPLATES: dict[QualityTemplate, tuple[QualitySpec, ...]] = {
    QualityTemplate.PALE_LAGER: (
        _spec(_S.BREWHOUSE, _P.ORIGINAL_EXTRACT, (10.5, 12.5), (11.0, 12.0), 11.5),
        _spec(_S.BREWHOUSE, _P.PH, (5.0, 5.5), (5.1, 5.4)),
        _spec(_S.BREWHOUSE, _P.BITTERNESS, (18.0, 32.0), (20.0, 30.0)),
        _spec(_S.BREWHOUSE, _P.COLOR, (6.0, 14.0), (7.0, 12.0)),
        _spec(_S.BREWHOUSE, _P.WORT_OXYGEN, (6.0, 14.0), (8.0, 12.0)),
        _spec(_S.BREWHOUSE, _P.FREE_AMINO_NITROGEN, (140.0, 240.0), (160.0, 220.0)),
        _spec(_S.MATURATION, _P.APPARENT_EXTRACT, (None, 2.5), (None, 2.2)),
        _spec(_S.MATURATION, _P.ALCOHOL_BY_VOLUME, (4.4, 5.4), (4.6, 5.2)),
        _spec(_S.MATURATION, _P.PH, (4.0, 4.7), (4.1, 4.6)),
        _spec(_S.MATURATION, _P.DIACETYL, (None, 80.0), (None, 50.0)),
        _spec(_S.MATURATION, _P.TURBIDITY_90, (None, 50.0), (None, 30.0)),
        _spec(_S.BRIGHT_BEER, _P.ORIGINAL_EXTRACT, (10.5, 12.5), (11.0, 12.0)),
        _spec(_S.BRIGHT_BEER, _P.ALCOHOL_BY_VOLUME, (4.5, 5.3), (4.7, 5.1), 4.9),
        _spec(_S.BRIGHT_BEER, _P.PH, (4.1, 4.6), (4.2, 4.5)),
        _spec(_S.BRIGHT_BEER, _P.COLOR, (5.0, 10.0), (6.0, 9.0)),
        _spec(_S.BRIGHT_BEER, _P.TURBIDITY_90, (None, 1.0), (None, 0.8)),
        _spec(_S.BRIGHT_BEER, _P.CARBON_DIOXIDE, (4.8, 5.6), (5.0, 5.4)),
        _spec(_S.BRIGHT_BEER, _P.DISSOLVED_OXYGEN, (None, 100.0), (None, 50.0)),
        _spec(_S.BRIGHT_BEER, _P.TEMPERATURE, (-1.0, 3.0), (0.0, 2.0)),
        _spec(_S.PACKAGED, _P.ALCOHOL_BY_VOLUME, (4.5, 5.3), (4.7, 5.1), 4.9),
        _spec(_S.PACKAGED, _P.PH, (4.1, 4.6), (4.2, 4.5)),
        _spec(_S.PACKAGED, _P.BITTERNESS, (14.0, 26.0), (16.0, 24.0), 20.0),
        _spec(_S.PACKAGED, _P.COLOR, (5.0, 10.0), (6.0, 9.0)),
        _spec(_S.PACKAGED, _P.TURBIDITY_90, (None, 1.0), (None, 0.8)),
        _spec(_S.PACKAGED, _P.CARBON_DIOXIDE, (4.8, 5.6), (5.0, 5.4)),
        _spec(_S.PACKAGED, _P.TOTAL_PACKAGE_OXYGEN, (None, 150.0), (None, 100.0)),
        _spec(_S.PACKAGED, _P.DIACETYL, (None, 50.0), (None, 30.0)),
        _spec(_S.PACKAGED, _P.FOAM_STABILITY, (200.0, None), (230.0, None)),
        _spec(_S.PACKAGED, _P.PASTEURIZATION_UNITS, (10.0, 40.0), (15.0, 30.0)),
    ),
}


def quality_template_specs(template: object) -> tuple[QualitySpec, ...]:
    """The preset specs of a profile template (a ``QualityTemplate`` or its code)."""
    return _TEMPLATES[_enum(QualityTemplate, "template", template)]
