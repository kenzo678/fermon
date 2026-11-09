from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest

from fermon.fermentation.domain import (
    Batch,
    BatchStatus,
    InvalidBatchError,
    InvalidBatchTransitionError,
    StyleTemplate,
    TargetRanges,
    template_targets,
)

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
BATCH_ID = UUID(int=1)
LATER = T0 + timedelta(days=1)


def targets(**overrides: Any) -> TargetRanges:
    values: dict[str, Any] = {"temperature_min": 18.0, "temperature_max": 21.0, "pressure_max": 1.0}
    return TargetRanges(**{**values, **overrides})


def make_batch(**overrides: Any) -> Batch:
    values: dict[str, Any] = {
        "id": BATCH_ID,
        "tank_id": " tank-1 ",
        "beer_name": " Pale Ale ",
        "style": "APA",
        "template": StyleTemplate.ALE,
        "targets": targets(),
        "status": BatchStatus.PLANNED,
        "planned_start": T0,
        "created_at": T0,
    }
    return Batch(**{**values, **overrides})


# --- TargetRanges ---------------------------------------------------------------------------


def test_valid_targets_keep_optional_fields_empty() -> None:
    ranges = targets()

    assert ranges.pressure_min is None
    assert ranges.expected_final_abv is None


@pytest.mark.parametrize(
    ("field", "overrides"),
    [
        ("temperature_max", {"temperature_min": 21.0}),  # min == max
        ("temperature_max", {"temperature_min": 22.0}),  # min > max
        ("temperature_min", {"temperature_min": -20.5}),  # below the physical limit
        ("temperature_max", {"temperature_max": 100.5}),  # above the physical limit
        ("pressure_max", {"pressure_max": 10.5}),
        ("pressure_max", {"pressure_max": -0.1}),
        ("pressure_min", {"pressure_min": 1.0}),  # min == max
        ("pressure_min", {"pressure_min": -1.0}),
        ("expected_final_abv", {"expected_final_abv": 20.5}),
        ("expected_final_abv", {"expected_final_abv": -1.0}),
        ("temperature_min", {"temperature_min": float("nan")}),
        ("temperature_max", {"temperature_max": True}),
        ("temperature_max", {"temperature_max": "21"}),
    ],
)
def test_invalid_targets_are_rejected_naming_the_field(
    field: str, overrides: dict[str, Any]
) -> None:
    with pytest.raises(InvalidBatchError) as exc:
        targets(**overrides)

    assert exc.value.field == field


def test_integers_are_accepted_and_stored_as_floats() -> None:
    ranges = targets(temperature_min=18, temperature_max=21, pressure_max=1)

    assert (ranges.temperature_min, ranges.temperature_max, ranges.pressure_max) == (18, 21, 1)
    assert isinstance(ranges.temperature_min, float)


# --- Templates ------------------------------------------------------------------------------


def test_ale_and_lager_presets_and_custom_has_none() -> None:
    assert template_targets(StyleTemplate.ALE) == TargetRanges(18.0, 21.0, 1.0, None, 5.0)
    assert template_targets(StyleTemplate.LAGER) == TargetRanges(8.0, 12.0, 1.2, None, 5.2)
    assert template_targets(StyleTemplate.CUSTOM) is None


# --- Batch construction ---------------------------------------------------------------------


def test_new_batch_is_normalized() -> None:
    batch = make_batch()

    assert batch.tank_id == "tank-1"
    assert batch.beer_name == "Pale Ale"
    assert batch.started_at is None and batch.finished_at is None
    assert batch.notes is None and batch.expected_end is None


@pytest.mark.parametrize(
    ("field", "overrides"),
    [
        ("id", {"id": "b1"}),
        ("tank_id", {"tank_id": "  "}),
        ("beer_name", {"beer_name": "  "}),
        ("style", {"style": ""}),
        ("template", {"template": "ipa"}),
        ("status", {"status": "done"}),
        ("targets", {"targets": None}),
        ("planned_start", {"planned_start": datetime(2026, 1, 1)}),
        ("created_at", {"created_at": datetime(2026, 1, 1)}),
        ("expected_end", {"expected_end": T0}),  # not after planned_start
        ("expected_end", {"expected_end": datetime(2026, 2, 1)}),  # naive
        ("started_at", {"started_at": T0}),  # planned batches have not started
        ("started_at", {"status": BatchStatus.ACTIVE}),  # active needs started_at
        ("finished_at", {"status": BatchStatus.ACTIVE, "started_at": T0, "finished_at": LATER}),
        ("finished_at", {"status": BatchStatus.FINISHED, "started_at": T0}),
    ],
)
def test_invalid_batches_are_rejected_naming_the_field(
    field: str, overrides: dict[str, Any]
) -> None:
    with pytest.raises(InvalidBatchError) as exc:
        make_batch(**overrides)

    assert exc.value.field == field


# --- Transitions ----------------------------------------------------------------------------


def test_start_then_finish_stamp_the_injected_time_without_mutating() -> None:
    planned = make_batch()

    active = planned.start(LATER)
    finished = active.finish(LATER + timedelta(days=7))

    assert planned.status is BatchStatus.PLANNED and planned.started_at is None
    assert (active.status, active.started_at, active.finished_at) == (
        BatchStatus.ACTIVE,
        LATER,
        None,
    )
    assert (finished.status, finished.started_at, finished.finished_at) == (
        BatchStatus.FINISHED,
        LATER,
        LATER + timedelta(days=7),
    )


@pytest.mark.parametrize(
    ("status", "action"),
    [
        (BatchStatus.ACTIVE, "start"),
        (BatchStatus.FINISHED, "start"),
        (BatchStatus.PLANNED, "finish"),
        (BatchStatus.FINISHED, "finish"),
    ],
)
def test_forbidden_transitions_raise(status: BatchStatus, action: str) -> None:
    batch = make_batch()
    if status is not BatchStatus.PLANNED:
        batch = batch.start(T0)
    if status is BatchStatus.FINISHED:
        batch = batch.finish(LATER)

    with pytest.raises(InvalidBatchTransitionError) as exc:
        getattr(batch, action)(LATER)

    assert (exc.value.batch_id, exc.value.status, exc.value.action) == (
        str(BATCH_ID),
        status,
        action,
    )


def test_transition_requires_an_aware_time() -> None:
    with pytest.raises(InvalidBatchError) as exc:
        make_batch().start(datetime(2026, 1, 2))

    assert exc.value.field == "started_at"


# --- Edition --------------------------------------------------------------------------------


def test_edit_planned_and_active_batches_revalidates() -> None:
    planned = make_batch()
    active = planned.start(LATER)

    edited = planned.edit(beer_name="  Stout ", notes="dry hop", targets=targets(pressure_max=2.0))
    still_active = active.edit(expected_end=LATER + timedelta(days=10))

    assert edited.beer_name == "Stout" and edited.notes == "dry hop"
    assert edited.targets.pressure_max == 2.0
    assert still_active.status is BatchStatus.ACTIVE
    assert still_active.started_at == LATER
    with pytest.raises(InvalidBatchError) as exc:
        planned.edit(expected_end=T0 - timedelta(days=1))
    assert exc.value.field == "expected_end"


def test_edit_can_clear_optional_fields_and_rejects_unknown_ones() -> None:
    batch = make_batch(notes="x", expected_end=LATER)

    cleared = batch.edit(notes=None, expected_end=None)

    assert cleared.notes is None and cleared.expected_end is None
    with pytest.raises(InvalidBatchError) as exc:
        batch.edit(status=BatchStatus.FINISHED)
    assert exc.value.field == "status"


def test_finished_batch_cannot_be_edited() -> None:
    finished = make_batch().start(T0).finish(LATER)

    with pytest.raises(InvalidBatchTransitionError) as exc:
        finished.edit(notes="late")

    assert exc.value.action == "edit"


def test_replace_still_validates() -> None:
    with pytest.raises(InvalidBatchError):
        replace(make_batch(), beer_name=" ")


# --- Version (optimistic concurrency token) ---------------------------------------------------


def test_a_new_batch_starts_at_version_one() -> None:
    assert make_batch().version == 1


def test_every_transition_and_edit_bumps_the_version() -> None:
    planned = make_batch()

    edited = planned.edit(notes="x")
    started = edited.start(T0)
    finished = started.finish(LATER)

    assert (edited.version, started.version, finished.version) == (2, 3, 4)
    assert planned.version == 1  # the original is immutable


def test_a_version_below_one_is_invalid() -> None:
    with pytest.raises(InvalidBatchError) as exc:
        make_batch(version=0)
    assert exc.value.field == "version"
