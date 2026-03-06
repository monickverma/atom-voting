"""
Atom Voting — Real-Time WebSocket Observability

Provides live streaming of the immutable ledger for hackathon demonstrations
and public verifiability without polling.
"""
from __future__ import annotations

import asyncio
import json
from enum import Enum
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(prefix="/api/v1", tags=["websockets"])


class EventType(str, Enum):
    VOTE_CAST = "VOTE_CAST"
    TALLY_STARTED = "TALLY_STARTED"
    TALLY_COMPLETED = "TALLY_COMPLETED"


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, event_type: EventType, data: dict[str, Any]) -> None:
        """Broadcast an event to all connected clients."""
        message = json.dumps({"event": event_type, "data": data})
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                # If a socket dies mid-broadcast, remove it quietly
                self.disconnect(connection)


# Global singleton manager for the application
manager = ConnectionManager()


@router.websocket("/ws/ledger")
async def websocket_ledger_endpoint(websocket: WebSocket) -> None:
    """
    Connect to this endpoint to receive live updates whenever a new
    anonymous VoteBlock is appended to the public ledger.
    """
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive, wait for client messages (if any)
            _ = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
