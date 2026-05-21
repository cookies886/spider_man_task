"""Task run state machine.

Centralizes:
  - Decision to launch a new run (concurrency policy)
  - Worker selection via dispatcher
  - State transitions on task.done / task.killed frames from worker
  - Retry / dependency-trigger orchestration
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session
from app.core.dispatcher import (
    list_online_candidates,
    pick_least_loaded,
    send_task_run,
)
from app.core.file_manager import file_manager
from app.core.metrics import record_run_terminal
from app.models.environment import Environment
from app.models.task import (
    ConcurrentPolicy,
    DependsOnStatus,
    NodeStrategy,
    RunStatus,
    Task,
    TaskDependency,
    TaskRun,
)
from app.models.worker import Worker, WorkerStatus

logger = logging.getLogger(__name__)

LOG_ROOT = Path(os.environ.get("TASK_LOG_ROOT", "/tmp/spiderman/taskLogs"))


def _log_path(task_id: uuid.UUID, run_id: uuid.UUID) -> str:
    p = LOG_ROOT / str(task_id) / f"{run_id}.log"
    p.parent.mkdir(parents=True, exist_ok=True)
    return str(p)


async def _running_count(session: AsyncSession, task_id: uuid.UUID) -> int:
    rows = await session.execute(
        select(TaskRun).where(
            TaskRun.task_id == task_id,
            TaskRun.status.in_(
                [RunStatus.PENDING, RunStatus.DISPATCHING, RunStatus.RUNNING]
            ),
        )
    )
    return len(rows.scalars().all())


def _candidate_filter(
    candidates: list[dict], task: Task
) -> tuple[list[dict], set[str]]:
    online_ids = {c["node_id"] for c in candidates}
    if task.node_strategy == NodeStrategy.MASTER:
        candidates = [c for c in candidates if c["type"] == "master_local"]
    elif task.node_strategy == NodeStrategy.SPECIFIC:
        target_node = (task.node_target or {}).get("node_id")
        candidates = [c for c in candidates if c["node_id"] == target_node]
    elif task.node_strategy == NodeStrategy.PLATFORM:
        target_os = (task.node_target or {}).get("platform", "").lower()
        candidates = [
            c for c in candidates if (c.get("os") or "").lower().startswith(target_os)
        ]
    elif task.node_strategy == NodeStrategy.GROUP:
        target_group = (task.node_target or {}).get("group_id")
        if target_group:
            candidates = [
                c for c in candidates if c.get("group_id") == str(target_group)
            ]
    elif task.node_strategy == NodeStrategy.MIXED:
        # MIXED = master_local + (preferred group if set) + remaining online.
        # Falls back to all online if no group is configured.
        target_group = (task.node_target or {}).get("group_id")
        if target_group:
            candidates = [
                c
                for c in candidates
                if c["type"] == "master_local"
                or c.get("group_id") == str(target_group)
            ]
    # AUTO: no filtering
    return candidates, online_ids


async def trigger_run(
    task_id: uuid.UUID, triggered_by: str = "scheduled"
) -> uuid.UUID | None:
    """Try to launch a new run. Returns the new run_id, or None if skipped."""
    async with async_session() as s:
        task = (
            await s.execute(select(Task).where(Task.id == task_id))
        ).scalar_one_or_none()
        if task is None or not task.is_active:
            return None

        running = await _running_count(s, task_id)
        if running >= task.max_concurrent:
            if task.concurrent_policy == ConcurrentPolicy.SKIP:
                run = TaskRun(
                    task_id=task_id,
                    status=RunStatus.SKIPPED,
                    started_at=datetime.now(timezone.utc),
                    finished_at=datetime.now(timezone.utc),
                    triggered_by=triggered_by,
                    error_msg="skipped: max_concurrent reached",
                )
                s.add(run)
                await s.commit()
                logger.info("task %s skipped (concurrent)", task_id)
                return None
            # QUEUE policy: continue to dispatch which may end up PENDING

        run = TaskRun(
            task_id=task_id,
            status=RunStatus.DISPATCHING,
            triggered_by=triggered_by,
        )
        s.add(run)
        await s.flush()
        run_id = run.id

        candidates = await list_online_candidates()
        candidates, _ = _candidate_filter(candidates, task)
        chosen = pick_least_loaded(
            candidates, online_ids={c["node_id"] for c in candidates}
        )

        if chosen is None:
            run.status = RunStatus.PENDING
            await s.commit()
            logger.info("task %s no worker available, run queued", task_id)
            return run_id

        node = (
            await s.execute(
                select(Worker).where(Worker.node_id == chosen["node_id"])
            )
        ).scalar_one()
        run.node_id = node.id
        run.log_file_path = _log_path(task_id, run_id)
        run.started_at = datetime.now(timezone.utc)
        run.status = RunStatus.RUNNING

        env_path = None
        if task.env_id:
            env = (
                await s.execute(
                    select(Environment).where(Environment.id == task.env_id)
                )
            ).scalar_one_or_none()
            if env:
                env_path = getattr(env, "install_path", None)

        zip_url = None
        expected_hash = None
        from sqlalchemy import select as _sel
        from app.models.project import Project

        proj = (
            await s.execute(_sel(Project).where(Project.id == task.project_id))
        ).scalar_one_or_none()
        if proj is not None:
            expected_hash = proj.current_hash
            # Worker fetches via internal endpoint; relative path is fine since worker
            # already knows MASTER_URL. Use protocol-less path; worker prefixes its own.
            zip_url = f"/api/v1/projects/{task.project_id}/zip?node_id={chosen['node_id']}"

        payload = {
            "run_id": str(run_id),
            "task_id": str(task_id),
            "command": task.command,
            "env_vars": {},
            "timeout_sec": task.timeout_sec,
            "expected_hash": expected_hash,
            "project_files_url": zip_url,
            "project_id": str(proj.id) if proj else None,
            "subdir": _project_subdir(proj, task),
            "env_path": env_path,
        }

        ok = await send_task_run(chosen["node_id"], payload)
        if not ok:
            run.status = RunStatus.PENDING
            run.error_msg = "dispatch failed"
            run.started_at = None
            run.node_id = None
        await s.commit()
        logger.info("task %s run %s dispatched to %s", task_id, run_id, chosen["node_id"])
        return run_id


def _project_subdir(project, task: Task) -> str:
    """Subdir under worker.work_dir where project files should be unpacked
    and where the command runs. Worker resolves relative to its own root."""
    if project is None:
        return "_no_project"
    work_path = (project.work_path or "/").lstrip("/")
    return f"{project.id}/{work_path}".rstrip("/")


async def _notify(event_str: str, run, task_name: str | None = None) -> None:
    try:
        from app.core.notifier import EventType, emit_event

        ev = {
            "task_failed": EventType.TASK_FAILED,
            "task_timeout": EventType.TASK_TIMEOUT,
            "task_killed": EventType.TASK_KILLED,
        }.get(event_str)
        if ev is None:
            return
        await emit_event(
            ev,
            {
                "run_id": str(run.id),
                "task_id": str(run.task_id),
                "task_name": task_name,
                "exit_code": run.exit_code,
                "error_msg": run.error_msg,
            },
        )
    except Exception:
        logger.exception("notify failed")


async def on_task_done(frame: dict) -> None:
    """Worker reported task.done. Update run + maybe retry / fan out to deps."""
    run_id_str = frame.get("run_id")
    if not run_id_str:
        return
    try:
        run_id = uuid.UUID(run_id_str)
    except (TypeError, ValueError):
        return

    exit_code = int(frame.get("exit_code", -1))

    retry_request: tuple[uuid.UUID, str] | None = None
    success_task: uuid.UUID | None = None

    async with async_session() as s:
        run = (
            await s.execute(select(TaskRun).where(TaskRun.id == run_id))
        ).scalar_one_or_none()
        if run is None:
            return
        if run.status not in (RunStatus.RUNNING, RunStatus.DISPATCHING):
            return

        run.exit_code = exit_code
        run.finished_at = datetime.now(timezone.utc)

        task = (
            await s.execute(select(Task).where(Task.id == run.task_id))
        ).scalar_one_or_none()
        max_retries = task.max_retries if task else 0

        notify_event: str | None = None
        task_name = task.name if task else None
        if exit_code == 0:
            run.status = RunStatus.SUCCESS
            success_task = run.task_id
        else:
            if run.retry_no < max_retries:
                run.status = RunStatus.FAILED
                run.error_msg = f"failed exit={exit_code}, will retry"
                retry_request = (run.task_id, run.retry_no + 1)
            else:
                run.status = RunStatus.FAILED
                run.error_msg = f"failed exit={exit_code}"
                notify_event = "task_failed"

        # Metrics: count this terminal status + record duration if known.
        dur = None
        if run.started_at and run.finished_at:
            dur = (run.finished_at - run.started_at).total_seconds()
        record_run_terminal(run.status, dur)

        await s.commit()

    if notify_event:
        await _notify(notify_event, run, task_name)

    if retry_request is not None:
        new_id = await trigger_run(retry_request[0], triggered_by="retry")
        if new_id is not None:
            async with async_session() as s:
                nr = (
                    await s.execute(select(TaskRun).where(TaskRun.id == new_id))
                ).scalar_one()
                nr.retry_no = retry_request[1]
                await s.commit()

    if success_task is not None:
        await _trigger_dependents(success_task, RunStatus.SUCCESS)


async def on_task_killed(frame: dict) -> None:
    run_id_str = frame.get("run_id")
    if not run_id_str:
        return
    try:
        run_id = uuid.UUID(run_id_str)
    except (TypeError, ValueError):
        return
    reason = frame.get("reason") or "killed"

    task_name = None
    async with async_session() as s:
        run = (
            await s.execute(select(TaskRun).where(TaskRun.id == run_id))
        ).scalar_one_or_none()
        if run is None:
            return
        run.status = (
            RunStatus.TIMEOUT if reason == "timeout" else RunStatus.KILLED
        )
        run.finished_at = datetime.now(timezone.utc)
        run.error_msg = reason
        task = (
            await s.execute(select(Task).where(Task.id == run.task_id))
        ).scalar_one_or_none()
        task_name = task.name if task else None

        dur = None
        if run.started_at and run.finished_at:
            dur = (run.finished_at - run.started_at).total_seconds()
        record_run_terminal(run.status, dur)

        await s.commit()

    await _notify(
        "task_timeout" if reason == "timeout" else "task_killed", run, task_name
    )
    await _trigger_dependents(run.task_id, RunStatus.FAILED)


async def _trigger_dependents(
    upstream_task_id: uuid.UUID, completed_status: RunStatus
) -> None:
    async with async_session() as s:
        rows = await s.execute(
            select(TaskDependency).where(
                TaskDependency.upstream_task_id == upstream_task_id
            )
        )
        deps = rows.scalars().all()
    for dep in deps:
        if (
            dep.on_status == DependsOnStatus.SUCCESS
            and completed_status != RunStatus.SUCCESS
        ):
            continue
        try:
            await trigger_run(dep.task_id, triggered_by="dependency")
        except Exception:
            logger.exception("failed to fan out to %s", dep.task_id)
