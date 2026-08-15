import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.auth.dependencies import get_user_id_from_token
from app.database.database import LocalSession
from app.database.models import RoadIssue
from app.websocket.manager import manager
from app.websocket.schemas import IssueBroadcastMessage, IssueBroadcastPayload

logger = logging.getLogger("urban_pulse.websocket")

router = APIRouter()


@router.websocket("/api/v1/ws/map")
async def map_websocket(websocket: WebSocket, token: str | None = None):
    if not token:
        await websocket.close(code=4401)
        return

    db = LocalSession()
    try:
        user_id = get_user_id_from_token(token, db)
        if user_id is None:
            await websocket.close(code=4401)
            return

        await manager.connect_map(websocket)

        try:
            # Send currently relevant (non-resolved) issues on connect.
            current_issues = db.query(RoadIssue).filter(RoadIssue.status != "resolved").all()
            for issue in current_issues:
                await websocket.send_json(
                    IssueBroadcastMessage(
                        type="issue_created",
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
                )

            # Keep the connection open; live updates arrive via manager.broadcast_to_map,
            # triggered from the device channel. We still need to read from the socket
            # so disconnects are detected promptly.
            while True:
                try:
                    await websocket.receive_text()
                except ValueError:
                    continue

        except WebSocketDisconnect:
            pass

    finally:
        manager.disconnect_map(websocket)
        db.close()
