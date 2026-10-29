from dataclasses import dataclass
from datetime import datetime

from fermon.fermentation.application.ports import ReadingRepository
from fermon.fermentation.domain import InvalidReadingError, MeasurementType, Reading


@dataclass(frozen=True, slots=True)
class IngestReadingCommand:
    tank_id: str
    sensor_id: str
    measurement: str
    value: float
    unit: str
    recorded_at: datetime


class IngestReading:
    def __init__(self, repository: ReadingRepository) -> None:
        self._repository = repository

    async def execute(self, command: IngestReadingCommand) -> Reading:
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
        await self._repository.add(reading)
        return reading
