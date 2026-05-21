"""Worker group CRUD."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.deps import require_perm
from app.models.worker import Worker, WorkerGroup
from app.schemas.worker_group import (
    WorkerGroupCreate,
    WorkerGroupRead,
    WorkerGroupUpdate,
)

router = APIRouter(prefix="/worker-groups", tags=["worker-groups"])


async def _serialize(session: AsyncSession, group: WorkerGroup) -> WorkerGroupRead:
    count = (
        await session.execute(
            select(func.count(Worker.id)).where(Worker.group_id == group.id)
        )
    ).scalar() or 0
    return WorkerGroupRead(
        id=group.id,
        created_at=group.created_at,
        updated_at=group.updated_at,
        name=group.name,
        description=group.description,
        tags=group.tags or [],
        worker_count=int(count),
    )


@router.get(
    "",
    response_model=list[WorkerGroupRead],
    dependencies=[Depends(require_perm("worker_group.read"))],
)
async def list_worker_groups(session: AsyncSession = Depends(get_session)):
    rows = await session.execute(select(WorkerGroup).order_by(WorkerGroup.name.asc()))
    groups = rows.scalars().all()
    out: list[WorkerGroupRead] = []
    for g in groups:
        out.append(await _serialize(session, g))
    return out


@router.post(
    "",
    response_model=WorkerGroupRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_perm("worker_group.manage"))],
)
async def create_worker_group(
    body: WorkerGroupCreate, session: AsyncSession = Depends(get_session)
):
    g = WorkerGroup(
        name=body.name,
        description=body.description,
        tags=body.tags or [],
    )
    session.add(g)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="group name already exists")
    await session.refresh(g)
    out = await _serialize(session, g)
    await session.commit()
    return out


@router.patch(
    "/{group_id}",
    response_model=WorkerGroupRead,
    dependencies=[Depends(require_perm("worker_group.manage"))],
)
async def update_worker_group(
    group_id: uuid.UUID,
    body: WorkerGroupUpdate,
    session: AsyncSession = Depends(get_session),
):
    g = (
        await session.execute(select(WorkerGroup).where(WorkerGroup.id == group_id))
    ).scalar_one_or_none()
    if g is None:
        raise HTTPException(status_code=404, detail="group not found")
    if body.name is not None:
        g.name = body.name
    if body.description is not None:
        g.description = body.description
    if body.tags is not None:
        g.tags = body.tags
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="group name already exists")
    await session.refresh(g)
    out = await _serialize(session, g)
    await session.commit()
    return out


@router.delete(
    "/{group_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_perm("worker_group.manage"))],
)
async def delete_worker_group(
    group_id: uuid.UUID, session: AsyncSession = Depends(get_session)
):
    g = (
        await session.execute(select(WorkerGroup).where(WorkerGroup.id == group_id))
    ).scalar_one_or_none()
    if g is None:
        raise HTTPException(status_code=404, detail="group not found")
    # FK is ON DELETE SET NULL — workers will be re-pooled to no group automatically.
    await session.delete(g)
    await session.commit()
