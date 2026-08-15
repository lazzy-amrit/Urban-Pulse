from datetime import datetime

from pydantic import BaseModel


class RoadIssueOut(BaseModel):
    id: str
    latitude: float
    longitude: float
    status: str
    classification: str
    confidence: float
    severity: float
    report_count: int
    unique_device_count: int
    first_seen: datetime
    last_seen: datetime

    class Config:
        from_attributes = True
