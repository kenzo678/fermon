import dataclasses
import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from fermon.fermentation.application.ports import BatchRepository, TankRepository
from fermon.fermentation.domain import (
    ActiveBatchConflictError,
    Batch,
    BatchNotFoundError,
    BatchStatus,
    ConcurrentBatchUpdateError,
    InvalidBatchError,
    StyleTemplate,
    TankNotFoundError,
    TargetRanges,
    normalize_id,
    template_targets,
)

logger = logging.getLogger(__name__)

AfterFinished = Callable[[Batch], Awaitable[None]]
"""Called with each batch right after it was finished."""

Clock = Callable[[], datetime]
"""Returns the current timezone-aware time; injected so time-dependent rules are testable."""

_REQUIRED_TARGETS = ("temperature_min", "temperature_max", "pressure_max")
_TARGET_FIELDS = tuple(f.name for f in dataclasses.fields(TargetRanges))


def merge_targets(base: TargetRanges | None, overrides: Mapping[str, Any] | None) -> TargetRanges:
    """``base`` with the given fields replaced; mandatory fields must end up present."""
    merged: dict[str, Any] = dataclasses.asdict(base) if base is not None else {}
    for field, value in (overrides or {}).items():
        if field not in _TARGET_FIELDS:
            raise InvalidBatchError(field, "is not a target range")
        merged[field] = value
    for field in _REQUIRED_TARGETS:
        if merged.get(field) is None:
            raise InvalidBatchError(field, "is required")
    return TargetRanges(**merged)


@dataclass(frozen=True, slots=True)
class CreateBatchCommand:
    tank_id: str
    beer_name: str
    style: str
    template: StyleTemplate
    targets: Mapping[str, Any] | None = None
    planned_start: datetime | None = None
    expected_end: datetime | None = None
    notes: str | None = None


class CreateBatch:
    def __init__(
        self,
        batches: BatchRepository,
        tanks: TankRepository,
        clock: Clock,
        new_id: Callable[[], UUID] = uuid4,
    ) -> None:
        self._batches = batches
        self._tanks = tanks
        self._clock = clock
        self._new_id = new_id

    async def execute(self, command: CreateBatchCommand) -> Batch:
        tank_id = normalize_id("tank_id", command.tank_id)
        if await self._tanks.get(tank_id) is None:
            raise TankNotFoundError(tank_id)
        try:
            template = StyleTemplate(command.template)
        except ValueError:
            raise InvalidBatchError("template", "must be one of ale, lager, custom") from None
        now = self._clock()
        batch = Batch(
            id=self._new_id(),
            tank_id=tank_id,
            beer_name=command.beer_name,
            style=command.style,
            template=template,
            targets=merge_targets(template_targets(template), command.targets),
            status=BatchStatus.PLANNED,
            planned_start=command.planned_start or now,
            expected_end=command.expected_end,
            notes=command.notes,
            created_at=now,
        )
        await self._batches.add(batch)
        return batch


async def _load(batches: BatchRepository, batch_id: UUID) -> Batch:
    batch = await batches.get(batch_id)
    if batch is None:
        raise BatchNotFoundError(str(batch_id))
    return batch


class UpdateBatch:
    def __init__(self, batches: BatchRepository) -> None:
        self._batches = batches

    async def execute(
        self, batch_id: UUID, changes: Mapping[str, Any], expected_version: int | None = None
    ) -> Batch:
        """Apply a partial edit; ``targets`` is merged over the current ranges field by field.

        With ``expected_version`` the edit applies only to that revision (if-match semantics).
        """
        batch = await _load(self._batches, batch_id)
        if expected_version is not None and expected_version != batch.version:
            raise ConcurrentBatchUpdateError(str(batch_id))
        fields = dict(changes)
        if "targets" in fields:
            fields["targets"] = merge_targets(batch.targets, fields["targets"])
        updated = batch.edit(**fields)
        if dataclasses.replace(updated, version=batch.version) == batch:
            # Nothing actually changed (empty patch, null/empty targets, identical values): don't
            # write, so other clients' versions stay valid.
            return batch
        await self._batches.update(updated)
        return updated


class StartBatch:
    def __init__(self, batches: BatchRepository, clock: Clock) -> None:
        self._batches = batches
        self._clock = clock

    async def execute(self, batch_id: UUID) -> Batch:
        batch = await _load(self._batches, batch_id)
        started = batch.start(self._clock())
        active = await self._batches.get_active(batch.tank_id)
        if active is not None and active.id != batch.id:
            raise ActiveBatchConflictError(batch.tank_id)
        # The repository enforces the invariant too, so a concurrent start still conflicts.
        await self._batches.update(started)
        return started


class FinishBatch:
    def __init__(
        self,
        batches: BatchRepository,
        clock: Clock,
        after_finished: AfterFinished | None = None,
    ) -> None:
        self._batches = batches
        self._clock = clock
        self._after_finished = after_finished

    async def execute(self, batch_id: UUID) -> Batch:
        finished = (await _load(self._batches, batch_id)).finish(self._clock())
        await self._batches.update(finished)
        await self._run_hook(finished)
        return finished

    async def _run_hook(self, batch: Batch) -> None:
        """Best-effort side effect (e.g. resolving the batch's alerts) of a finished batch.

        The batch is already committed, so a hook failure must not fail the finish; a periodic
        sweep repairs whatever the hook missed.
        """
        if self._after_finished is None:
            return
        try:
            await self._after_finished(batch)
        except Exception:
            logger.error(
                "after-finish hook failed for batch=%s; the batch was finished",
                batch.id,
                exc_info=True,
            )


class GetBatch:
    def __init__(self, batches: BatchRepository) -> None:
        self._batches = batches

    async def execute(self, batch_id: UUID) -> Batch:
        return await _load(self._batches, batch_id)


class ListBatches:
    def __init__(self, batches: BatchRepository) -> None:
        self._batches = batches

    async def execute(
        self, tank_id: str | None = None, status: BatchStatus | None = None
    ) -> list[Batch]:
        cleaned = normalize_id("tank_id", tank_id) if tank_id is not None else None
        return await self._batches.list(tank_id=cleaned, status=status)


class GetActiveBatch:
    def __init__(self, batches: BatchRepository) -> None:
        self._batches = batches

    async def execute(self, tank_id: str) -> Batch | None:
        return await self._batches.get_active(normalize_id("tank_id", tank_id))
