"""WS-based task dispatcher.

Slice 1 surface: pure functions that pick a worker and ship a task.run frame
through the in-memory registry. Slice 4 reattaches this to the Task model
state machine and APScheduler.
"""
from __future__ import annotations

import logging
from typing import Iterable

from sqlalchemy import select

from app.core.database import async_session
from app.core.worker_registry import registry
from app.models.worker import Worker, WorkerStatus

logger = logging.getLogger(__name__)


def pick_least_loaded(
    candidates: Iterable[dict],
    online_ids: set[str],
) -> dict | None:
    """Return the candidate with the smallest current_tasks/max_slots ratio
    among those that are currently online. None if no candidate is online."""
    best: dict | None = None
    best_ratio: float = 2.0
    for c in candidates:
        if c["node_id"] not in online_ids:
            continue
        ratio = (c.get("current_tasks") or 0) / max(c.get("max_slots") or 1, 1)
        if ratio < best_ratio:
            best = c
            best_ratio = ratio
    return best


async def send_task_run(node_id: str, payload: dict) -> bool:
    """Send a task.run frame to the named worker. Returns True on success."""
    frame = {"type": "task.run", **payload}
    return await registry.send(node_id, frame)


async def send_task_kill(node_id: str, run_id: str, signal: str = "TERM") -> bool:
    return await registry.send(
        node_id,
        {"type": "task.kill", "run_id": run_id, "signal": signal},
    )


async def list_online_candidates() -> list[dict]:
    """Read DB workers that are registry-online and ONLINE/BUSY in DB."""
    online_ids = set(registry.online_node_ids())
    if not online_ids:
        return []
    async with async_session() as s:
        rows = await s.execute(
            select(Worker).where(
                Worker.node_id.in_(online_ids),
                Worker.status.in_([WorkerStatus.ONLINE, WorkerStatus.BUSY]),
            )
        )
        out = []
        for w in rows.scalars().all():
            out.append(
                {
                    "node_id": w.node_id,
                    "current_tasks": w.current_tasks,
                    "max_slots": w.max_slots,
                    "type": w.type,
                    "os": w.os,
                    "labels": w.labels or [],
                    "group_id": str(w.group_id) if w.group_id else None,
                }
            )
        return out
