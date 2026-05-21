"""Slice 1 acceptance: dispatch an echo task to master_local and observe its log.

Requires the docker compose stack running. Run with:
    pytest tests/e2e -v
"""
from __future__ import annotations

import asyncio
import json
import os
import uuid

import httpx
import pytest
import websockets


MASTER = os.environ.get("E2E_MASTER", "http://localhost:8000")
MASTER_WS = MASTER.replace("http://", "ws://").replace("https://", "wss://")
NODE_ID = os.environ.get("MASTER_LOCAL_NODE_ID", "master-local")


@pytest.mark.asyncio
async def test_slice1_echo_roundtrip():
    async with httpx.AsyncClient(base_url=MASTER, timeout=10.0) as c:
        r = await c.post(
            "/api/v1/auth/login",
            json={
                "username": os.environ.get("ADMIN_USERNAME", "admin"),
                "password": os.environ.get("ADMIN_PASSWORD", "admin123"),
            },
        )
        r.raise_for_status()
        token = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Wait for master-local to come online
        for _ in range(30):
            r = await c.get("/api/v1/workers", headers=headers)
            workers = r.json().get("items", [])
            ml = next((w for w in workers if w["node_id"] == NODE_ID), None)
            if ml and ml["status"] == "online":
                break
            await asyncio.sleep(1)
        else:
            pytest.fail("master-local never came online")

    run_id = str(uuid.uuid4())
    received_lines: list[str] = []
    done = asyncio.Event()

    async def consumer():
        url = f"{MASTER_WS}/ws/runs/{run_id}/logs"
        async with websockets.connect(url) as ws:
            try:
                while True:
                    msg = await asyncio.wait_for(ws.recv(), timeout=15)
                    frame = json.loads(msg)
                    if "line" in frame:
                        received_lines.append(frame["line"])
                    if frame.get("event") == "task_done" or frame.get("type") == "task.done":
                        done.set()
                        return
            except asyncio.TimeoutError:
                return

    async with httpx.AsyncClient(base_url=MASTER, timeout=10.0) as c:
        c_task = asyncio.create_task(consumer())
        await asyncio.sleep(0.5)
        r = await c.post(
            "/api/v1/_debug/dispatch",
            json={
                "node_id": NODE_ID,
                "run_id": run_id,
                "command": "echo hello-from-slice1",
                "timeout_sec": 30,
            },
            headers=headers,
        )
        r.raise_for_status()
        try:
            await asyncio.wait_for(done.wait(), timeout=15)
        except asyncio.TimeoutError:
            pass
        c_task.cancel()
        try:
            await c_task
        except (asyncio.CancelledError, Exception):
            pass

    assert "hello-from-slice1" in received_lines
