"""MQTT wire contract: topic ``{prefix}/tanks/{tank_id}/readings`` + JSON payload."""

import re
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from fermon.fermentation.application import IngestReadingCommand


class InvalidTopicError(ValueError):
    """Raised when a topic does not follow ``{prefix}/tanks/{tank_id}/readings``."""


class ReadingMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sensor_id: str
    measurement: str
    value: Annotated[float, Field(strict=True, allow_inf_nan=False)]
    unit: str
    recorded_at: AwareDatetime


def parse_topic(topic: str, prefix: str) -> str:
    """Return the tank id carried by ``topic`` or raise ``InvalidTopicError``."""
    match = re.fullmatch(rf"{re.escape(prefix)}/tanks/([^/+#]+)/readings", topic)
    if match is None:
        raise InvalidTopicError(f"unexpected topic '{topic}'")
    return match.group(1)


def to_command(tank_id: str, message: ReadingMessage) -> IngestReadingCommand:
    return IngestReadingCommand(
        tank_id=tank_id,
        sensor_id=message.sensor_id,
        measurement=message.measurement,
        value=message.value,
        unit=message.unit,
        recorded_at=message.recorded_at,
    )
