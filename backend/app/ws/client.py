"""Browser-side WS endpoint for task run log streaming.

Subscribes to Redis channel `task.log.{run_id}` and forwards every message
as JSON text to the connected browser. Closes when the browser disconnects.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.redis import get_redis

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/runs/{run_id}/logs")
async def stream_run_logs(websocket: WebSocket, run_id: str):
    await websocket.accept()
    redis = await get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(f"task.log.{run_id}")
    listener: asyncio.Task | None = None

    async def forward():
        async for msg in pubsub.listen():
            if msg.get("type") != "message":
                continue
            data = msg.get("data")
            if isinstance(data, (bytes, bytearray)):
                data = data.decode("utf-8")
            try:
                await websocket.send_text(data)
            except Exception:
                logger.exception("forward failed")
                return

    try:
        listener = asyncio.create_task(forward())
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        if listener and not listener.done():
            listener.cancel()
        try:
            await pubsub.unsubscribe(f"task.log.{run_id}")
            await pubsub.aclose()
        except Exception:
            pass
        await redis.aclose()
