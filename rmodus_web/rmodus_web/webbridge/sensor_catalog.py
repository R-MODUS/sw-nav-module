"""Sensor metadata helpers used by the websocket sensors dashboard."""

from dataclasses import dataclass
from typing import Iterable, List, Optional


@dataclass(frozen=True)
class SensorDefinition:
    sensor_type: str
    sensor_id: str
    topic: str
    label: str
    frame_id: Optional[str] = None
    message_type: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "sensor_type": self.sensor_type,
            "sensor_id": self.sensor_id,
            "topic": self.topic,
            "label": self.label,
            "frame_id": self.frame_id,
            "message_type": self.message_type,
        }


def flatten_sensor_catalog(groups: Iterable[Iterable[SensorDefinition]]) -> List[dict]:
    return [sensor.as_dict() for group in groups for sensor in group]
