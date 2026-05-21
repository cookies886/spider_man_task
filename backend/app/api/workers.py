import secrets
import uuid

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.deps import require_perm
from app.models.worker import Worker, WorkerGroup, WorkerStatus
from app.schemas.common import PaginatedResponse
from app.schemas.worker import (
    WorkerCreate,
    WorkerCreated,
    WorkerRead,
    WorkerUpdate,
    generate_api_key,
)

router = APIRouter(prefix="/workers", tags=["workers"])


@router.get("", response_model=PaginatedResponse, dependencies=[Depends(require_perm("worker.read"))])
async def list_workers(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    total = (await session.execute(select(func.count(Worker.id)))).scalar() or 0
    skip = (page - 1) * page_size
    rows = await session.execute(
        select(Worker)
        .order_by(Worker.last_heartbeat.desc().nullslast())
        .offset(skip)
        .limit(page_size)
    )
    items = [WorkerRead.model_validate(w) for w in rows.scalars().all()]
    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size,
    )


@router.post(
    "",
    response_model=WorkerCreated,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_perm("worker.manage"))],
)
async def create_worker(body: WorkerCreate, session: AsyncSession = Depends(get_session)):
    if body.group_id is not None:
        exists = (
            await session.execute(
                select(WorkerGroup).where(WorkerGroup.id == body.group_id)
            )
        ).scalar_one_or_none()
        if exists is None:
            raise HTTPException(status_code=400, detail="group_id not found")
    api_key = generate_api_key()
    api_key_hash = bcrypt.hashpw(api_key.encode(), bcrypt.gensalt()).decode()
    node_id = body.name.lower().replace(" ", "-") + "-" + secrets.token_hex(4)
    w = Worker(
        node_id=node_id,
        name=body.name,
        hostname=body.hostname,
        ip=body.ip,
        port=body.port,
        type=body.type,
        max_slots=body.max_slots,
        labels=body.labels or [],
        status=WorkerStatus.OFFLINE,
        api_key_hash=api_key_hash,
        group_id=body.group_id,
    )
    session.add(w)
    await session.flush()
    await session.refresh(w)
    await session.commit()
    return WorkerCreated(
        id=w.id,
        created_at=w.created_at,
        updated_at=w.updated_at,
        node_id=w.node_id,
        name=w.name,
        hostname=w.hostname,
        ip=w.ip,
        port=w.port,
        type=w.type,
        group_id=w.group_id,
        api_key=api_key,
    )


@router.patch(
    "/{worker_id}",
    response_model=WorkerRead,
    dependencies=[Depends(require_perm("worker.manage"))],
)
async def update_worker(
    worker_id: uuid.UUID,
    body: WorkerUpdate,
    session: AsyncSession = Depends(get_session),
):
    w = (
        await session.execute(select(Worker).where(Worker.id == worker_id))
    ).scalar_one_or_none()
    if w is None:
        raise HTTPException(status_code=404, detail="Worker not found")
    payload = body.model_dump(exclude_unset=True)
    if "group_id" in payload and payload["group_id"] is not None:
        exists = (
            await session.execute(
                select(WorkerGroup).where(WorkerGroup.id == payload["group_id"])
            )
        ).scalar_one_or_none()
        if exists is None:
            raise HTTPException(status_code=400, detail="group_id not found")
    for k, v in payload.items():
        setattr(w, k, v)
    await session.flush()
    await session.refresh(w)
    out = WorkerRead.model_validate(w)
    await session.commit()
    return out


@router.delete(
    "/{worker_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_perm("worker.manage"))],
)
async def delete_worker(worker_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    row = await session.execute(select(Worker).where(Worker.id == worker_id))
    w = row.scalar_one_or_none()
    if not w:
        raise HTTPException(status_code=404, detail="Worker not found")
    await session.delete(w)
    await session.commit()


@router.post("/{worker_id}/task-result", deprecated=True, status_code=410)
async def deprecated_task_result(worker_id: uuid.UUID):
    return {"detail": "task results now flow over /ws/worker; this endpoint is removed"}
