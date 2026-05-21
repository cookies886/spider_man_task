"""In-memory registry of live Worker WebSocket connections.

A single instance lives at app.core.worker_registry.registry. Thread-safety:
register/unregister are protected by an asyncio.Lock. send is best-effort.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class WSLike(Protocol):
    async def send_json(self, data: Any) -> None: ...
    async def close(self, code: int = 1000) -> None: ...


class WorkerRegistry:
    def __init__(self) -> None:
        self._conns: dict[str, WSLike] = {}
        self._lock = asyncio.Lock()

    async def register(self, node_id: str, ws: WSLike) -> None:
        async with self._lock:
            old = self._conns.get(node_id)
            self._conns[node_id] = ws
        if old is not None and old is not ws:
            try:
                await old.close(code=4000)
            except Exception:
                logger.exception("error closing old ws for %s", node_id)

    async def unregister(self, node_id: str, ws: WSLike | None = None) -> None:
        async with self._lock:
            cur = self._conns.get(node_id)
            if ws is None or cur is ws:
                self._conns.pop(node_id, None)

    def is_online(self, node_id: str) -> bool:
        return node_id in self._conns

    def online_node_ids(self) -> list[str]:
        return list(self._conns.keys())

    async def send(self, node_id: str, frame: Any) -> bool:
        ws = self._conns.get(node_id)
        if ws is None:
            return False
        try:
            await ws.send_json(frame)
            return True
        except Exception:
            logger.exception("send to node %s failed", node_id)
            await self.unregister(node_id, ws)
            return False


registry = WorkerRegistry()
