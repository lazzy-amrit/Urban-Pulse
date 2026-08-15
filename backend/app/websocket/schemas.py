from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Device -> backend (incoming)
# ---------------------------------------------------------------------------

class SensorEventPayload(BaseModel):
    device_id: str
    timestamp: datetime
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    speed: float | None = Field(default=None, ge=0)
    heading: float | None = None
    event_type: str
    confidence: float = Field(ge=0, le=1)
    severity: float = Field(ge=0, le=1)
    sensor_source: str | None = None
    features: dict[str, Any] | None = None


class SensorEventMessage(BaseModel):
    type: Literal["sensor_event"]
    payload: SensorEventPayload


class HeartbeatPayload(BaseModel):
    device_id: str


class HeartbeatMessage(BaseModel):
    type: Literal["heartbeat"]
    payload: HeartbeatPayload


class SensorStatusPayload(BaseModel):
    device_id: str
    sensors_active: list[str] | None = None
    battery_level: float | None = Field(default=None, ge=0, le=1)


class SensorStatusMessage(BaseModel):
    type: Literal["sensor_status"]
    payload: SensorStatusPayload


class VisionDetection(BaseModel):
    class_: str = Field(alias="class")
    confidence: float = Field(ge=0, le=1)
    bbox: list[float] | None = None

    class Config:
        populate_by_name = True


class VisionEventPayload(BaseModel):
    device_id: str
    timestamp: datetime
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    detections: list[VisionDetection] = Field(default_factory=list)


class VisionEventMessage(BaseModel):
    type: Literal["vision_event"]
    payload: VisionEventPayload


# ---------------------------------------------------------------------------
# Backend -> device (outgoing)
# ---------------------------------------------------------------------------

class EventAckPayload(BaseModel):
    event_id: str
    issue_id: str
    status: str


class EventAckMessage(BaseModel):
    type: Literal["event_ack"] = "event_ack"
    payload: EventAckPayload


# ---------------------------------------------------------------------------
# Backend -> map/frontend (outgoing)
# ---------------------------------------------------------------------------

class IssueBroadcastPayload(BaseModel):
    id: str
    latitude: float
    longitude: float
    classification: str
    status: str
    confidence: float
    severity: float
    report_count: int
    unique_device_count: int


class IssueBroadcastMessage(BaseModel):
    type: Literal["issue_created", "issue_updated", "issue_resolved"]
    payload: IssueBroadcastPayload
