"""Worker reverse-WS endpoint. Workers connect here with bearer api_key."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

import bcrypt
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.core.database import async_session
from app.core.redis import get_redis
from app.core.worker_registry import registry
from app.models.task import TaskRun
from app.models.worker import Worker, WorkerStatus

logger = logging.getLogger(__name__)
router = APIRouter()

# Cache run_id -> log_file_path to avoid a DB roundtrip per log line.
_LOG_PATH_CACHE: dict[str, str] = {}


async def _resolve_log_path(run_id: str) -> str | None:
    cached = _LOG_PATH_CACHE.get(run_id)
    if cached is not None:
        return cached
    async with async_session() as s:
        try:
            uid = run_id  # accept str; SQLAlchemy will cast
            r = (
                await s.execute(select(TaskRun).where(TaskRun.id == uid))
            ).scalar_one_or_none()
        except Exception:
            return None
    if r is None or r.log_file_path is None:
        return None
    _LOG_PATH_CACHE[run_id] = r.log_file_path
    return r.log_file_path


async def _authenticate(node_id: str, token: str) -> Worker | None:
    async with async_session() as session:
        row = await session.execute(select(Worker).where(Worker.node_id == node_id))
        worker = row.scalar_one_or_none()
        if worker is None:
            return None
        if not bcrypt.checkpw(token.encode(), worker.api_key_hash.encode()):
            return None
        return worker


@router.websocket("/ws/worker")
async def worker_ws(
    websocket: WebSocket,
    node_id: str = Query(...),
    token: str = Query(...),
):
    worker = await _authenticate(node_id, token)
    if worker is None:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    await registry.register(node_id, websocket)

    async with async_session() as s:
        w = (await s.execute(select(Worker).where(Worker.node_id == node_id))).scalar_one()
        w.status = WorkerStatus.ONLINE
        w.last_heartbeat = datetime.now(timezone.utc)
        await s.commit()

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                frame = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("bad json from %s", node_id)
                continue

            t = frame.get("type")
            if t == "register":
                await _handle_register(node_id, frame)
                await websocket.send_json({"type": "register.ack", "node_id": node_id})
            elif t == "heartbeat":
                await _handle_heartbeat(node_id, frame)
            elif t == "task.log":
                await _handle_task_log(frame)
            elif t == "task.done":
                await _handle_task_done(frame)
            elif t == "task.killed":
                await _handle_task_killed(frame)
            else:
                logger.info("unknown frame type=%s from %s", t, node_id)
    except WebSocketDisconnect:
        logger.info("worker %s disconnected", node_id)
    finally:
        await registry.unregister(node_id, websocket)
        async with async_session() as s:
            row = await s.execute(select(Worker).where(Worker.node_id == node_id))
            w = row.scalar_one_or_none()
            if w is not None:
                w.status = WorkerStatus.OFFLINE
                await s.commit()


async def _handle_register(node_id: str, frame: dict) -> None:
    async with async_session() as s:
        w = (await s.execute(select(Worker).where(Worker.node_id == node_id))).scalar_one()
        w.os = frame.get("os")
        w.arch = frame.get("arch")
        w.python_version = frame.get("python_version")
        if frame.get("ip"):
            w.ip = frame["ip"]
        await s.commit()


_LAST_METRIC_AT: dict[str, datetime] = {}


async def _handle_heartbeat(node_id: str, frame: dict) -> None:
    from app.models.worker import WorkerMetric

    now = datetime.now(timezone.utc)
    async with async_session() as s:
        w = (await s.execute(select(Worker).where(Worker.node_id == node_id))).scalar_one()
        w.cpu_usage = float(frame.get("cpu", 0.0))
        w.mem_usage = float(frame.get("mem", 0.0))
        w.current_tasks = int(frame.get("running", 0))
        w.last_heartbeat = now
        w.status = WorkerStatus.ONLINE

        # Persist a metric sample at most every 30s
        last = _LAST_METRIC_AT.get(node_id)
        if last is None or (now - last).total_seconds() >= 30:
            s.add(
                WorkerMetric(
                    worker_id=w.id,
                    ts=now,
                    cpu_pct=float(frame.get("cpu", 0.0)),
                    mem_pct=float(frame.get("mem", 0.0)),
                    disk_pct=float(frame.get("disk", 0.0)),
                    net_in_bps=int(frame.get("net_in", 0)),
                    net_out_bps=int(frame.get("net_out", 0)),
                    running_tasks=int(frame.get("running", 0)),
                )
            )
            _LAST_METRIC_AT[node_id] = now
        await s.commit()


async def _handle_task_log(frame: dict) -> None:
    run_id = frame.get("run_id")
    if not run_id:
        return

    # Stamp on receive if worker didn't supply one
    if not frame.get("ts"):
        frame["ts"] = datetime.now(timezone.utc).isoformat()

    redis = await get_redis()
    try:
        await redis.publish(f"task.log.{run_id}", json.dumps(frame))
    finally:
        await redis.aclose()

    # Append to disk for historical filtering. Best-effort; failures must not
    # break the live stream.
    try:
        path = await _resolve_log_path(run_id)
        if path:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            line = json.dumps(
                {
                    "ts": frame["ts"],
                    "stream": frame.get("stream") or "stdout",
                    "line": frame.get("line", ""),
                },
                ensure_ascii=False,
            )
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
    except Exception:
        logger.exception("failed to persist log line for run %s", run_id)


async def _handle_task_done(frame: dict) -> None:
    from app.core.runs import on_task_done

    await on_task_done(frame)
    redis = await get_redis()
    try:
        await redis.publish(
            f"task.log.{frame.get('run_id')}",
            json.dumps({**frame, "event": "task_done"}),
        )
        await redis.publish(
            "spiderman:events", json.dumps({**frame, "event": "task_done"})
        )
    finally:
        await redis.aclose()


async def _handle_task_killed(frame: dict) -> None:
    from app.core.runs import on_task_killed

    await on_task_killed(frame)
    redis = await get_redis()
    try:
        await redis.publish(
            f"task.log.{frame.get('run_id')}",
            json.dumps({**frame, "event": "task_killed"}),
        )
        await redis.publish(
            "spiderman:events", json.dumps({**frame, "event": "task_killed"})
        )
    finally:
        await redis.aclose()
