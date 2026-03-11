from __future__ import annotations

import asyncio
import json

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.core.redis import get_redis

logger = structlog.get_logger()

router = APIRouter()


class ConnectionManager:
    """Manages active WebSocket connections."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("WebSocket client connected", total=len(self.active_connections))

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info("WebSocket client disconnected", total=len(self.active_connections))

    async def broadcast(self, message: dict):
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)
        for conn in disconnected:
            self.active_connections.remove(conn)


manager = ConnectionManager()

# Redis channels to subscribe to for real-time events
CHANNELS = [
    "portfolio:update",
    "trade:executed",
    "trade:pending_approval",
    "order:status",
    "risk:alert",
    "risk:circuit_breaker",
    "risk:kill_switch",
    "signal:generated",
]


async def redis_subscriber():
    """Subscribe to Redis pub/sub channels and broadcast to WebSocket clients."""
    try:
        redis = await get_redis()
        pubsub = redis.pubsub()
        await pubsub.subscribe(*CHANNELS)

        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                except (json.JSONDecodeError, TypeError):
                    data = {"raw": str(message["data"])}

                event = {
                    "channel": message["channel"],
                    "data": data,
                }
                await manager.broadcast(event)
    except Exception as e:
        logger.error("Redis subscriber error", error=str(e))


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates.

    Clients receive events from Redis pub/sub channels:
    - portfolio:update - Portfolio value changes
    - trade:executed - Trade fills
    - trade:pending_approval - New trades needing approval
    - order:status - Order status changes
    - risk:alert - Risk warnings
    - risk:circuit_breaker - Circuit breaker state changes
    - risk:kill_switch - Kill switch activation/deactivation
    - signal:generated - New trading signals
    """
    await manager.connect(websocket)

    # Start Redis subscriber if not already running
    subscriber_task = asyncio.create_task(redis_subscriber())

    try:
        while True:
            # Keep connection alive, handle client messages
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                # Handle ping/pong for keepalive
                if msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    finally:
        subscriber_task.cancel()
