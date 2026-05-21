"""Tasks API."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import (
    user_can_read_project,
    user_can_write_project,
    user_owns_project,
)
from app.core.database import get_session
from app.core.deps import require_perm
from app.core.dispatcher import send_task_kill
from app.core.rate_limit import api_rate_limit
from app.core.runs import trigger_run
from app.core.scheduler import scheduler_service
from app.models.project import Project, ProjectCollaborator
from app.models.task import (
    RunStatus,
    Task,
    TaskDependency,
    TaskRun,
)
from app.models.user import User
from app.models.worker import Worker
from sqlalchemy import or_
from app.schemas.common import PaginatedResponse
from app.schemas.task import (
    DependencyAdd,
    TaskCreate,
    TaskDetail,
    TaskRead,
    TaskRunRead,
    TaskUpdate,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _task_visibility_clause(user: User):
    """Tasks are visible if their project is — owner OR collaborator OR superuser."""
    if user.is_superuser:
        return None
    accessible_project_subq = select(Project.id).where(
        or_(
            Project.owner_id == user.id,
            Project.id.in_(
                select(ProjectCollaborator.project_id).where(
                    ProjectCollaborator.user_id == user.id
                )
            ),
        )
    )
    return Task.project_id.in_(accessible_project_subq)


@router.get(
    "",
    response_model=PaginatedResponse,
)
async def list_tasks(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    project_id: uuid.UUID | None = None,
    is_active: bool | None = None,
    search: str | None = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_perm("task.read")),
):
    q = select(Task)
    cq = select(func.count(Task.id))
    visibility = _task_visibility_clause(user)
    if visibility is not None:
        q = q.where(visibility)
        cq = cq.where(visibility)
    if project_id:
        q = q.where(Task.project_id == project_id)
        cq = cq.where(Task.project_id == project_id)
    if is_active is not None:
        q = q.where(Task.is_active == is_active)
        cq = cq.where(Task.is_active == is_active)
    if search:
        q = q.where(Task.name.ilike(f"%{search}%"))
        cq = cq.where(Task.name.ilike(f"%{search}%"))
    total = (await session.execute(cq)).scalar() or 0
    skip = (page - 1) * page_size
    rows = await session.execute(
        q.order_by(Task.created_at.desc()).offset(skip).limit(page_size)
    )
    items = [TaskRead.model_validate(t) for t in rows.scalars().all()]
    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size,
    )


async def _hydrate_detail(session: AsyncSession, task: Task) -> TaskDetail:
    deps = (
        await session.execute(
            select(TaskDependency.upstream_task_id).where(
                TaskDependency.task_id == task.id
            )
        )
    ).scalars().all()
    base = TaskRead.model_validate(task).model_dump()
    return TaskDetail(
        **base,
        depends_on=list(deps),
        next_run_at=scheduler_service.next_run(task.id),
    )


@router.get(
    "/{task_id}",
    response_model=TaskDetail,
)
async def get_task(
    task_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_perm("task.read")),
):
    t = (
        await session.execute(select(Task).where(Task.id == task_id))
    ).scalar_one_or_none()
    if t is None:
        raise HTTPException(404, "task not found")
    if not await user_can_read_project(session, user, t.project_id):
        raise HTTPException(404, "task not found")
    return await _hydrate_detail(session, t)


@router.post(
    "",
    response_model=TaskDetail,
    status_code=status.HTTP_201_CREATED,
    # 300 / min from same IP — abusers blocked, humans/tests unaffected
    dependencies=[Depends(api_rate_limit("task_write", 300, 60))],
)
async def create_task(
    body: TaskCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_perm("task.create")),
):
    if not await user_can_write_project(session, user, body.project_id):
        raise HTTPException(404, "project not found")
    if (
        await session.execute(select(Task).where(Task.name == body.name))
    ).scalar_one_or_none():
        raise HTTPException(409, "task name already exists")
    t = Task(
        name=body.name,
        description=body.description,
        project_id=body.project_id,
        env_id=body.env_id,
        command=body.command,
        schedule_type=body.schedule_type,
        schedule_config=body.schedule_config or {},
        node_strategy=body.node_strategy,
        node_target=body.node_target or {},
        max_concurrent=body.max_concurrent,
        concurrent_policy=body.concurrent_policy,
        max_retries=body.max_retries,
        timeout_sec=body.timeout_sec,
        is_active=body.is_active,
        tags=body.tags or [],
        owner_id=user.id,
    )
    session.add(t)
    await session.flush()
    if body.depends_on:
        for upstream in body.depends_on:
            session.add(
                TaskDependency(task_id=t.id, upstream_task_id=upstream)
            )
    await session.commit()
    await session.refresh(t)
    scheduler_service.register(t)
    return await _hydrate_detail(session, t)


@router.get("/{task_id}/dag")
async def task_dag(
    task_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_perm("task.read")),
):
    """Return the dependency subgraph centered on this task.

    Includes the task itself, all direct upstream + downstream tasks (1 hop).
    Used by the frontend DAG visualization.
    """
    task = (
        await session.execute(select(Task).where(Task.id == task_id))
    ).scalar_one_or_none()
    if task is None:
        raise HTTPException(404, "task not found")
    if not await user_can_read_project(session, user, task.project_id):
        raise HTTPException(404, "task not found")

    # Direct upstream
    up_rows = (
        await session.execute(
            select(Task, TaskDependency.on_status)
            .join(TaskDependency, TaskDependency.upstream_task_id == Task.id)
            .where(TaskDependency.task_id == task_id)
        )
    ).all()
    # Direct downstream
    dn_rows = (
        await session.execute(
            select(Task, TaskDependency.on_status)
            .join(TaskDependency, TaskDependency.task_id == Task.id)
            .where(TaskDependency.upstream_task_id == task_id)
        )
    ).all()

    nodes = {
        str(task.id): {
            "id": str(task.id),
            "name": task.name,
            "is_active": task.is_active,
            "role": "self",
        }
    }
    edges = []
    for t, status in up_rows:
        nodes[str(t.id)] = {
            "id": str(t.id),
            "name": t.name,
            "is_active": t.is_active,
            "role": "upstream",
        }
        edges.append(
            {"source": str(t.id), "target": str(task.id), "on_status": str(status)}
        )
    for t, status in dn_rows:
        if str(t.id) not in nodes:
            nodes[str(t.id)] = {
                "id": str(t.id),
                "name": t.name,
                "is_active": t.is_active,
                "role": "downstream",
            }
        edges.append(
            {"source": str(task.id), "target": str(t.id), "on_status": str(status)}
        )
    return {"nodes": list(nodes.values()), "edges": edges}


@router.put(
    "/{task_id}",
    response_model=TaskDetail,
)
async def update_task(
    task_id: uuid.UUID,
    body: TaskUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_perm("task.update")),
):
    t = (
        await session.execute(select(Task).where(Task.id == task_id))
    ).scalar_one_or_none()
    if t is None:
        raise HTTPException(404, "task not found")
    if not await user_can_write_project(session, user, t.project_id):
        raise HTTPException(404, "task not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(t, field, value)
    await session.commit()
    await session.refresh(t)
    scheduler_service.refresh(t)
    return await _hydrate_detail(session, t)


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_task(
    task_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_perm("task.delete")),
):
    t = (
        await session.execute(select(Task).where(Task.id == task_id))
    ).scalar_one_or_none()
    if t is None:
        raise HTTPException(404, "task not found")
    # Only project owner or superuser can delete tasks (collaborators are read/write but not destructive)
    if not await user_owns_project(session, user, t.project_id):
        raise HTTPException(403, "only project owner or superuser can delete tasks")
    scheduler_service.unregister(task_id)
    await session.delete(t)
    await session.commit()


@router.post(
    "/{task_id}/pause",
    response_model=TaskDetail,
)
async def pause_task(
    task_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_perm("task.update")),
):
    t = (
        await session.execute(select(Task).where(Task.id == task_id))
    ).scalar_one_or_none()
    if t is None:
        raise HTTPException(404, "task not found")
    if not await user_can_write_project(session, user, t.project_id):
        raise HTTPException(404, "task not found")
    t.is_active = False
    await session.commit()
    scheduler_service.unregister(task_id)
    await session.refresh(t)
    return await _hydrate_detail(session, t)


@router.post(
    "/{task_id}/resume",
    response_model=TaskDetail,
)
async def resume_task(
    task_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_perm("task.update")),
):
    t = (
        await session.execute(select(Task).where(Task.id == task_id))
    ).scalar_one_or_none()
    if t is None:
        raise HTTPException(404, "task not found")
    if not await user_can_write_project(session, user, t.project_id):
        raise HTTPException(404, "task not found")
    t.is_active = True
    await session.commit()
    scheduler_service.register(t)
    await session.refresh(t)
    return await _hydrate_detail(session, t)


@router.post(
    "/{task_id}/run",
)
async def run_now(
    task_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_perm("task.execute")),
):
    t = (
        await session.execute(select(Task).where(Task.id == task_id))
    ).scalar_one_or_none()
    if t is None:
        raise HTTPException(404, "task not found")
    if not await user_can_write_project(session, user, t.project_id):
        raise HTTPException(404, "task not found")
    run_id = await trigger_run(task_id, triggered_by="manual")
    if run_id is None:
        raise HTTPException(409, "run not started (skipped or task inactive)")
    return {"run_id": str(run_id)}


@router.get(
    "/{task_id}/runs",
    response_model=PaginatedResponse,
    dependencies=[Depends(require_perm("task.read"))],
)
async def list_runs(
    task_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    cq = select(func.count(TaskRun.id)).where(TaskRun.task_id == task_id)
    total = (await session.execute(cq)).scalar() or 0
    skip = (page - 1) * page_size
    rows = await session.execute(
        select(TaskRun)
        .where(TaskRun.task_id == task_id)
        .order_by(desc(TaskRun.created_at))
        .offset(skip)
        .limit(page_size)
    )
    items = [TaskRunRead.model_validate(r) for r in rows.scalars().all()]
    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size,
    )


@router.get(
    "/runs/{run_id}",
    response_model=TaskRunRead,
    dependencies=[Depends(require_perm("task.read"))],
)
async def get_run(
    run_id: uuid.UUID, session: AsyncSession = Depends(get_session)
):
    r = (
        await session.execute(select(TaskRun).where(TaskRun.id == run_id))
    ).scalar_one_or_none()
    if r is None:
        raise HTTPException(404, "run not found")
    return TaskRunRead.model_validate(r)


def _stream_to_level(stream: str | None) -> str:
    return "ERROR" if stream == "stderr" else "INFO"


@router.get(
    "/runs/{run_id}/logs",
)
async def get_run_logs(
    run_id: uuid.UUID,
    level: Literal["INFO", "ERROR"] | None = None,
    keyword: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=1000, ge=1, le=10000),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_perm("task.read")),
):
    """Filtered + paginated historical log lines for a run.

    Reads the JSONL sink populated by `app.ws.worker._handle_task_log`. Returns
    the line list plus total matched count (for pagination).
    """
    r = (
        await session.execute(select(TaskRun).where(TaskRun.id == run_id))
    ).scalar_one_or_none()
    if r is None:
        raise HTTPException(404, "run not found")
    project_id = (
        await session.execute(select(Task.project_id).where(Task.id == r.task_id))
    ).scalar()
    if project_id is None or not await user_can_read_project(session, user, project_id):
        raise HTTPException(404, "run not found")

    if r.log_file_path is None or not os.path.exists(r.log_file_path):
        return {"items": [], "total": 0, "offset": offset, "limit": limit}

    keyword_lc = keyword.lower() if keyword else None
    since_iso = since.isoformat() if since else None
    until_iso = until.isoformat() if until else None

    items: list[dict] = []
    matched = 0

    with open(r.log_file_path, "r", encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.rstrip("\n")
            if not raw:
                continue
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError:
                # legacy plain-text — synthesize record
                rec = {"ts": "", "stream": "stdout", "line": raw}
            line_level = _stream_to_level(rec.get("stream"))
            if level and line_level != level:
                continue
            if keyword_lc and keyword_lc not in (rec.get("line", "").lower()):
                continue
            ts = rec.get("ts") or ""
            if since_iso and ts and ts < since_iso:
                continue
            if until_iso and ts and ts > until_iso:
                continue
            matched += 1
            if matched > offset and len(items) < limit:
                items.append(
                    {
                        "ts": ts,
                        "stream": rec.get("stream") or "stdout",
                        "level": line_level,
                        "line": rec.get("line", ""),
                    }
                )

    return {"items": items, "total": matched, "offset": offset, "limit": limit}


@router.get(
    "/runs/{run_id}/log",
    dependencies=[Depends(require_perm("task.read"))],
)
async def download_run_log(
    run_id: uuid.UUID, session: AsyncSession = Depends(get_session)
):
    r = (
        await session.execute(select(TaskRun).where(TaskRun.id == run_id))
    ).scalar_one_or_none()
    if r is None or r.log_file_path is None:
        raise HTTPException(404, "log not found")
    if not os.path.exists(r.log_file_path):
        raise HTTPException(404, "log file missing on disk")
    return FileResponse(
        r.log_file_path,
        filename=f"{run_id}.log",
        media_type="text/plain",
    )


@router.post(
    "/runs/{run_id}/kill",
    dependencies=[Depends(require_perm("task.execute"))],
)
async def kill_run(
    run_id: uuid.UUID, session: AsyncSession = Depends(get_session)
):
    r = (
        await session.execute(select(TaskRun).where(TaskRun.id == run_id))
    ).scalar_one_or_none()
    if r is None:
        raise HTTPException(404, "run not found")
    if r.status not in (RunStatus.RUNNING, RunStatus.DISPATCHING):
        raise HTTPException(409, f"run is {r.status}, not running")
    if r.node_id is None:
        raise HTTPException(409, "run has no assigned node yet")
    worker = (
        await session.execute(select(Worker).where(Worker.id == r.node_id))
    ).scalar_one()
    ok = await send_task_kill(worker.node_id, str(run_id), "TERM")
    if not ok:
        raise HTTPException(500, "kill frame send failed")
    return {"ok": True}


@router.post("/batch/pause")
async def batch_pause(
    body: dict,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_perm("task.update")),
):
    """Batch pause: body={'ids': [uuid]}. Returns counts of {paused, skipped}."""
    return await _batch_active(body.get("ids") or [], False, session, user)


@router.post("/batch/resume")
async def batch_resume(
    body: dict,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_perm("task.update")),
):
    return await _batch_active(body.get("ids") or [], True, session, user)


@router.post("/batch/delete")
async def batch_delete(
    body: dict,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_perm("task.delete")),
):
    ids = body.get("ids") or []
    deleted = 0
    skipped = 0
    for tid in ids:
        try:
            tid_uuid = uuid.UUID(tid)
        except (ValueError, TypeError):
            skipped += 1
            continue
        t = (
            await session.execute(select(Task).where(Task.id == tid_uuid))
        ).scalar_one_or_none()
        if t is None:
            skipped += 1
            continue
        if not await user_owns_project(session, user, t.project_id):
            skipped += 1
            continue
        scheduler_service.unregister(tid_uuid)
        await session.delete(t)
        deleted += 1
    await session.commit()
    return {"deleted": deleted, "skipped": skipped}


async def _batch_active(
    ids: list, active: bool, session: AsyncSession, user: User
) -> dict:
    affected = 0
    skipped = 0
    for tid in ids:
        try:
            tid_uuid = uuid.UUID(tid)
        except (ValueError, TypeError):
            skipped += 1
            continue
        t = (
            await session.execute(select(Task).where(Task.id == tid_uuid))
        ).scalar_one_or_none()
        if t is None or not await user_can_write_project(session, user, t.project_id):
            skipped += 1
            continue
        t.is_active = active
        if active:
            scheduler_service.register(t)
        else:
            scheduler_service.unregister(tid_uuid)
        affected += 1
    await session.commit()
    return {"affected": affected, "skipped": skipped}


@router.post(
    "/{task_id}/dependencies",
    dependencies=[Depends(require_perm("task.update"))],
)
async def add_dependency(
    task_id: uuid.UUID,
    body: DependencyAdd,
    session: AsyncSession = Depends(get_session),
):
    if task_id == body.upstream_task_id:
        raise HTTPException(400, "task cannot depend on itself")
    queue = [body.upstream_task_id]
    seen: set[uuid.UUID] = set()
    while queue:
        cur = queue.pop()
        if cur in seen:
            continue
        seen.add(cur)
        if cur == task_id:
            raise HTTPException(400, "dependency cycle detected")
        ups = (
            await session.execute(
                select(TaskDependency.upstream_task_id).where(
                    TaskDependency.task_id == cur
                )
            )
        ).scalars().all()
        queue.extend(ups)
    session.add(
        TaskDependency(
            task_id=task_id,
            upstream_task_id=body.upstream_task_id,
            on_status=body.on_status,
        )
    )
    await session.commit()
    return {"ok": True}


@router.delete(
    "/{task_id}/dependencies/{upstream_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_perm("task.update"))],
)
async def remove_dependency(
    task_id: uuid.UUID,
    upstream_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    await session.execute(
        TaskDependency.__table__.delete().where(
            TaskDependency.task_id == task_id,
            TaskDependency.upstream_task_id == upstream_id,
        )
    )
    await session.commit()
