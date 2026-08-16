import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from starlette.websockets import WebSocketState

from app.auth.dependencies import get_user_id_from_token
from app.database.database import LocalSession
from app.database.models import Device
from app.devices.service import touch_device_last_seen
from app.intelligence import classifier
from app.intelligence.fallback import fallback_interpret
from app.issues.service import ingest_sensor_event, apply_ai_refinement, get_prior_counts
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

pipeline_stats = {"events": 0, "gemini_refined": 0, "fallback_only": 0}


def _issue_message(issue, kind: str) -> dict:
    return IssueBroadcastMessage(
        type=kind,
        payload=IssueBroadcastPayload(
            id=issue.id, latitude=issue.latitude, longitude=issue.longitude,
            classification=issue.classification, status=issue.status,
            confidence=issue.confidence, severity=issue.severity,
            report_count=issue.report_count, unique_device_count=issue.unique_device_count,
            created_at=issue.created_at, updated_at=issue.updated_at,
        ),
    ).model_dump()


async def _safe_send(websocket: WebSocket, message: dict) -> bool:
    if websocket.client_state != WebSocketState.CONNECTED:
        return False
    try:
        await websocket.send_json(message)
        return True
    except Exception as exc:
        logger.info("send failed, dropping connection: %s", exc)
        return False


async def _refine_in_background(report_id: str, prior_report_count: int, prior_unique_device_count: int, payload) -> None:
    refined = await classifier.refine_with_gemini(
        event_type=payload.event_type,
        phone_confidence=payload.confidence,
        phone_severity=payload.severity,
        sensor_source=payload.sensor_source,
        features=payload.features,
        speed=payload.speed,
        heading=payload.heading,
        prior_report_count=prior_report_count,
        prior_unique_device_count=prior_unique_device_count,
    )
    if refined is None:
        return

    db = LocalSession()
    try:
        result = apply_ai_refinement(db, report_id, refined)
        if result is None:
            return
        _, issue = result
        pipeline_stats["gemini_refined"] += 1
        await manager.broadcast_to_map(_issue_message(issue, "issue_updated"))
    except Exception as exc:
        logger.warning("background refinement failed for report %s: %s", report_id, exc)
    finally:
        db.close()


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
                    continue

                message_type = raw.get("type")

                try:
                    if message_type == "sensor_event":
                        msg = SensorEventMessage.model_validate(raw)
                        payload = msg.payload
                        if payload.device_id != device_id:
                            continue

                        # Fast, local, no network — this is what makes the ack instant.
                        # Prior counts come from whatever issue already sits at this
                        # location, so repeat/independent evidence is reflected even
                        # when Gemini never gets a chance to refine this report.
                        prior_report_count, prior_unique_device_count = get_prior_counts(
                            db, payload.latitude, payload.longitude
                        )
                        interpretation = fallback_interpret(
                            phone_confidence=payload.confidence,
                            phone_severity=payload.severity,
                            speed=payload.speed,
                            features=payload.features,
                            prior_report_count=prior_report_count,
                            prior_unique_device_count=prior_unique_device_count,
                        )
                        report, issue = ingest_sensor_event(
                            db, device=device, timestamp=payload.timestamp,
                            latitude=payload.latitude, longitude=payload.longitude,
                            speed=payload.speed, heading=payload.heading,
                            event_type=payload.event_type,
                            phone_confidence=payload.confidence, phone_severity=payload.severity,
                            sensor_source=payload.sensor_source, features=payload.features,
                            interpretation=interpretation,
                        )
                        pipeline_stats["events"] += 1
                        pipeline_stats["fallback_only"] += 1

                        ok = await _safe_send(
                            websocket,
                            EventAckMessage(payload=EventAckPayload(
                                event_id=report.id, issue_id=issue.id, status=issue.status,
                            )).model_dump(),
                        )
                        if not ok:
                            break

                        is_new = issue.report_count == 1
                        await manager.broadcast_to_map(_issue_message(issue, "issue_created" if is_new else "issue_updated"))

                        # Gemini (slow, external) happens off the receive loop.
                        asyncio.create_task(
                            _refine_in_background(report.id, issue.report_count, issue.unique_device_count, payload)
                        )

                    elif message_type == "heartbeat":
                        HeartbeatMessage.model_validate(raw)
                        touch_device_last_seen(db, device)

                    elif message_type == "sensor_status":
                        SensorStatusMessage.model_validate(raw)
                        touch_device_last_seen(db, device)

                    elif message_type == "vision_event":
                        msg = VisionEventMessage.model_validate(raw)
                        payload = msg.payload
                        detections = [d.model_dump(by_alias=True) for d in payload.detections]
                        issue = apply_vision_evidence(db, payload.latitude, payload.longitude, detections)
                        if issue is not None:
                            await manager.broadcast_to_map(_issue_message(issue, "issue_updated"))

                    else:
                        logger.info("unknown message type: %s", message_type)

                except ValidationError as exc:
                    logger.info("validation error from device %s: %s", device_id, exc)
                    continue
                except Exception as exc:
                    logger.warning("error handling message from device %s: %s", device_id, exc)
                    continue

        except WebSocketDisconnect:
            pass
        finally:
            manager.disconnect_device(device_id)

    finally:
        db.close()
