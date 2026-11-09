import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime

from fermon.fermentation.application.ports import ReadingRepository, TankRepository
from fermon.fermentation.domain import InvalidReadingError, MeasurementType, Reading

logger = logging.getLogger(__name__)

AfterCreated = Callable[[Reading], Awaitable[None]]
"""Called with each newly stored reading (never for duplicates)."""


@dataclass(frozen=True, slots=True)
class IngestReadingCommand:
    tank_id: str
    sensor_id: str
    measurement: str
    value: float
    unit: str
    recorded_at: datetime


@dataclass(frozen=True, slots=True)
class IngestResult:
    """Outcome of an ingest: the stored reading and whether this call created it."""

    reading: Reading
    created: bool


class IngestReading:
    def __init__(
        self,
        repository: ReadingRepository,
        tanks: TankRepository,
        after_created: AfterCreated | None = None,
    ) -> None:
        self._repository = repository
        self._tanks = tanks
        self._after_created = after_created

    async def execute(self, command: IngestReadingCommand) -> IngestResult:
        try:
            measurement = MeasurementType(command.measurement)
        except ValueError:
            raise InvalidReadingError(
                "measurement", f"unknown measurement '{command.measurement}'"
            ) from None

        reading = Reading(
            tank_id=command.tank_id,
            sensor_id=command.sensor_id,
            measurement=measurement,
            value=command.value,
            unit=command.unit,
            recorded_at=command.recorded_at,
        )
        # Register first: a stored reading then never lacks its tank. Idempotent, and only
        # reached for a valid reading, so a rejected message never creates a tank.
        await self._tanks.ensure(reading.tank_id, reading.recorded_at)
        if await self._repository.add(reading):
            await self._run_hook(reading)
            return IngestResult(reading=reading, created=True)

        stored = await self._repository.get(
            reading.tank_id, reading.sensor_id, reading.measurement, reading.recorded_at
        )
        if stored is None:  # pragma: no cover - rows are never deleted by this system
            raise RuntimeError("reading reported as duplicate but not found")
        return IngestResult(reading=stored, created=False)

    async def _run_hook(self, reading: Reading) -> None:
        """Best-effort side effect (alert evaluation) of a stored reading.

        The reading is already committed, so a hook failure must neither fail the ingest nor make
        the MQTT consumer retry it (the retry would see a duplicate and skip the hook anyway).
        Hooks derive their state from stored data, so the next reading re-evaluates.
        """
        if self._after_created is None:
            return
        try:
            await self._after_created(reading)
        except Exception:
            logger.error(
                "after-ingest hook failed for tank=%s; the reading was stored",
                reading.tank_id,
                exc_info=True,
            )
