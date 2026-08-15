from datetime import datetime

from pydantic import BaseModel, Field


class DeviceUpsertRequest(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=128)
    platform: str = Field(min_length=1, max_length=32)
    app_version: str | None = None


class DeviceOut(BaseModel):
    id: str
    name: str
    platform: str
    app_version: str | None
    created_at: datetime
    last_seen: datetime

    class Config:
        from_attributes = True
