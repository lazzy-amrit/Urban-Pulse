"""
Tracks connected device and map WebSocket clients, and broadcasts issue
updates to all connected map clients. A failure on one socket must never
take down another connection or the server.
"""

import logging

from fastapi import WebSocket
from starlette.websockets import WebSocketState

logger = logging.getLogger("urban_pulse.websocket")


class ConnectionManager:
    def __init__(self):
        # device_id -> websocket (one active connection per device)
        self.device_connections: dict[str, WebSocket] = {}
        # arbitrary set of connected map/frontend clients
        self.map_connections: set[WebSocket] = set()

    # -- device channel ------------------------------------------------

    async def connect_device(self, device_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self.device_connections[device_id] = websocket
        logger.info("device websocket connected: %s", device_id)

    def disconnect_device(self, device_id: str) -> None:
        if self.device_connections.get(device_id) is not None:
            del self.device_connections[device_id]
            logger.info("device websocket disconnected: %s", device_id)

    # -- map channel ------------------------------------------------

    async def connect_map(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.map_connections.add(websocket)
        logger.info("map websocket connected (total=%d)", len(self.map_connections))

    def disconnect_map(self, websocket: WebSocket) -> None:
        self.map_connections.discard(websocket)
        logger.info("map websocket disconnected (total=%d)", len(self.map_connections))

    async def broadcast_to_map(self, message: dict) -> None:
        dead_sockets = []
        for socket in self.map_connections:
            if socket.client_state != WebSocketState.CONNECTED:
                dead_sockets.append(socket)
                continue
            try:
                await socket.send_json(message)
            except Exception as exc:  # noqa: BLE001 — one bad socket must not break the broadcast
                logger.warning("failed to send to map socket, dropping it: %s", exc)
                dead_sockets.append(socket)

        for socket in dead_sockets:
            self.map_connections.discard(socket)


manager = ConnectionManager()
