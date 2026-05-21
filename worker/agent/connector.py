"""Maintains a single WS reverse-connection to the Master with reconnect.

API:
    Connector(config, on_frame).run()  — never returns until cancelled.
    await Connector.send(frame)        — best-effort send, drops if not connected.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Awaitable, Callable
from urllib.parse import urlencode

import websockets

logger = logging.getLogger(__name__)

OnFrame = Callable[[dict], Awaitable[None]]


class Connector:
    def __init__(self, config, on_frame: OnFrame):
        self.cfg = config
        self.on_frame = on_frame
        self._ws = None
        self._lock = asyncio.Lock()

    @property
    def url(self) -> str:
        q = urlencode({"node_id": self.cfg.node_id, "token": self.cfg.api_key})
        return f"{self.cfg.master_url}/ws/worker?{q}"

    async def send(self, frame: dict) -> bool:
        async with self._lock:
            if self._ws is None:
                return False
            try:
                await self._ws.send(json.dumps(frame))
                return True
            except Exception:
                logger.exception("send failed")
                return False

    async def run_once(self) -> None:
        """Connect, pump inbound frames until disconnect. Used in tests."""
        async with websockets.connect(self.url) as ws:
            self._ws = ws
            try:
                async for msg in ws:
                    try:
                        frame = json.loads(msg)
                    except json.JSONDecodeError:
                        continue
                    try:
                        await self.on_frame(frame)
                    except Exception:
                        logger.exception("on_frame failed")
            finally:
                self._ws = None

    async def run(self) -> None:
        """Connect with exponential backoff, forever (until cancelled)."""
        backoff = 1
        while True:
            try:
                await self.run_once()
                backoff = 1
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("connection lost, retry in %ds", backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)
