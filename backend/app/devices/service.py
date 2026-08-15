from datetime import datetime

from sqlalchemy.orm import Session

from app.core.errors import forbidden
from app.database.models import Device


def upsert_device(
    db: Session,
    user_id: str,
    device_id: str,
    name: str,
    platform: str,
    app_version: str | None,
) -> Device:
    existing = db.query(Device).filter(Device.id == device_id).first()

    if existing is not None:
        if existing.user_id != user_id:
            # Device id belongs to a different user — never leak or hijack it.
            raise forbidden("This device is registered to another account.")
        existing.name = name
        existing.platform = platform
        existing.app_version = app_version
        existing.last_seen = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        return existing

    device = Device(
        id=device_id,
        user_id=user_id,
        name=name,
        platform=platform,
        app_version=app_version,
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


def list_devices(db: Session, user_id: str) -> list[Device]:
    return db.query(Device).filter(Device.user_id == user_id).order_by(Device.created_at.desc()).all()


def touch_device_last_seen(db: Session, device: Device) -> None:
    device.last_seen = datetime.utcnow()
    db.commit()
