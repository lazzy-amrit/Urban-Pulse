from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database.database import get_db
from app.database.models import User
from app.devices import service
from app.devices.schemas import DeviceUpsertRequest, DeviceOut

router = APIRouter(prefix="/api/v1/devices", tags=["devices"])


@router.post("", response_model=DeviceOut, status_code=201)
def upsert_device(
    body: DeviceUpsertRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    device = service.upsert_device(
        db,
        user_id=current_user.id,
        device_id=body.id,
        name=body.name,
        platform=body.platform,
        app_version=body.app_version,
    )
    return DeviceOut.model_validate(device)


@router.get("", response_model=list[DeviceOut])
def list_devices(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    devices = service.list_devices(db, current_user.id)
    return [DeviceOut.model_validate(d) for d in devices]
