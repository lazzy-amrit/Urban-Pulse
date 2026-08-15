import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.auth.dependencies import get_user_id_from_token
from app.database.database import LocalSession
from app.database.models import Device
from app.devices.service import touch_device_last_seen
from app.issues.service import ingest_sensor_event
from app.issues.vision import apply_vision_evidence
from app.websocket.manager import manager
from app.websocket.schemas import (
    SensorEventMessage,
    HeartbeatMessage,
    SensorStatusMessage,
    VisionEventMessage,
    EventAckMessage,
    EventAckPayload,
    IssueBroadcastMessage,
    IssueBroadcastPayload,
)

logger = logging.getLogger("urban_pulse.websocket")

router = APIRouter()


def _issue_broadcast_message(issue, event_kind: str) -> dict:
    return IssueBroadcastMessage(
        type=event_kind,
        payload=IssueBroadcastPayload(
            id=issue.id,
            latitude=issue.latitude,
            longitude=issue.longitude,
            classification=issue.classification,
            status=issue.status,
            confidence=issue.confidence,
            severity=issue.severity,
            report_count=issue.report_count,
            unique_device_count=issue.unique_device_count,
        ),
    ).model_dump()


@router.websocket("/api/v1/ws/device")
async def device_websocket(websocket: WebSocket, token: str | None = None, device_id: str | None = None):
    if not token or not device_id:
        await websocket.close(code=4401)
        return

    db = LocalSession()
    try:
        user_id = get_user_id_from_token(token, db)
        if user_id is None:
            await websocket.close(code=4401)
            return

        device = db.query(Device).filter(Device.id == device_id).first()
        if device is None or device.user_id != user_id:
            await websocket.close(code=4403)
            return

        await manager.connect_device(device_id, websocket)

        try:
            while True:
                try:
                    raw = await websocket.receive_json()
                except ValueError:
                    logger.info("device %s sent malformed JSON; ignoring message", device_id)
                    continue

                message_type = raw.get("type")

                try:
                    if message_type == "sensor_event":
                        msg = SensorEventMessage.model_validate(raw)
                        payload = msg.payload

                        if payload.device_id != device_id:
                            logger.info("device_id mismatch on sensor_event; ignoring")
                            continue

                        report, issue = ingest_sensor_event(
                            db,
                            device=device,
                            timestamp=payload.timestamp,
                            latitude=payload.latitude,
                            longitude=payload.longitude,
                            speed=payload.speed,
                            heading=payload.heading,
                            event_type=payload.event_type,
                            phone_confidence=payload.confidence,
                            phone_severity=payload.severity,
                            sensor_source=payload.sensor_source,
                            features=payload.features,
                        )

                        is_new_issue = issue.report_count == 1
                        await websocket.send_json(
                            EventAckMessage(
                                payload=EventAckPayload(
                                    event_id=report.id, issue_id=issue.id, status=issue.status
                                )
                            ).model_dump()
                        )
                        await manager.broadcast_to_map(
                            _issue_broadcast_message(
                                issue, "issue_created" if is_new_issue else "issue_updated"
                            )
                        )

                    elif message_type == "heartbeat":
                        HeartbeatMessage.model_validate(raw)
                        touch_device_last_seen(db, device)

                    elif message_type == "sensor_status":
                        SensorStatusMessage.model_validate(raw)
                        # Lightweight — currently just acknowledged via last_seen touch.
                        touch_device_last_seen(db, device)

                    elif message_type == "vision_event":
                        msg = VisionEventMessage.model_validate(raw)
                        payload = msg.payload
                        detections = [d.model_dump(by_alias=True) for d in payload.detections]
                        issue = apply_vision_evidence(
                            db, payload.latitude, payload.longitude, detections
                        )
                        if issue is not None:
                            await manager.broadcast_to_map(
                                _issue_broadcast_message(issue, "issue_updated")
                            )

                    else:
                        logger.info("unknown message type from device %s: %s", device_id, message_type)

                except ValidationError as exc:
                    logger.info("validation error from device %s: %s", device_id, exc)
                    continue
                except Exception as exc:  # noqa: BLE001 — never let one bad message kill the socket
                    logger.warning("error handling message from device %s: %s", device_id, exc)
                    continue

        except WebSocketDisconnect:
            pass
        finally:
            manager.disconnect_device(device_id)

    finally:
        db.close()
