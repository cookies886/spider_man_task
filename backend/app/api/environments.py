"""Environments + Python Versions + Mirror Sources API."""
from __future__ import annotations

import asyncio
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import (
    env_visibility_clause,
    user_can_read_env,
    user_can_write_env,
    user_owns_env,
)
from app.core.database import get_session
from app.core.deps import require_perm
from app.core.pyver_builder import build_python_version
from app.core.venv_manager import create_environment
from app.models.environment import (
    Environment,
    EnvironmentCollaborator,
    EnvStatus,
    MirrorSource,
    PythonVersion,
    PyVerStatus,
)
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.environment import (
    EnvironmentCreate,
    EnvironmentRead,
    EnvironmentUpdate,
    MirrorCreate,
    MirrorRead,
    PythonVersionCreate,
    PythonVersionRead,
)

router = APIRouter(tags=["envs"])


@router.get(
    "/python-versions",
    response_model=list[PythonVersionRead],
    dependencies=[Depends(require_perm("environment.read"))],
)
async def list_pyvers(session: AsyncSession = Depends(get_session)):
    rows = await session.execute(
        select(PythonVersion).order_by(PythonVersion.version)
    )
    return [PythonVersionRead.model_validate(p) for p in rows.scalars().all()]


@router.post(
    "/python-versions",
    response_model=PythonVersionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_pyver(
    body: PythonVersionCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_perm("environment.manage")),
):
    if (
        await session.execute(
            select(PythonVersion).where(PythonVersion.version == body.version)
        )
    ).scalar_one_or_none():
        raise HTTPException(409, "version already exists")
    pv = PythonVersion(
        version=body.version,
        tarball_url=body.tarball_url,
        status=PyVerStatus.DOWNLOADING,
        owner_id=user.id,
    )
    session.add(pv)
    await session.commit()
    await session.refresh(pv)
    asyncio.create_task(build_python_version(pv.id))
    return PythonVersionRead.model_validate(pv)


@router.delete(
    "/python-versions/{version_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_perm("environment.manage"))],
)
async def delete_pyver(
    version_id: uuid.UUID, session: AsyncSession = Depends(get_session)
):
    pv = (
        await session.execute(
            select(PythonVersion).where(PythonVersion.id == version_id)
        )
    ).scalar_one_or_none()
    if pv is None:
        raise HTTPException(404, "python version not found")
    if pv.is_default:
        raise HTTPException(409, "cannot delete default version")
    await session.delete(pv)
    await session.commit()


@router.post(
    "/python-versions/{version_id}/set-default",
    response_model=PythonVersionRead,
    dependencies=[Depends(require_perm("environment.manage"))],
)
async def set_default_pyver(
    version_id: uuid.UUID, session: AsyncSession = Depends(get_session)
):
    pv = (
        await session.execute(
            select(PythonVersion).where(PythonVersion.id == version_id)
        )
    ).scalar_one_or_none()
    if pv is None:
        raise HTTPException(404, "python version not found")
    if pv.status != PyVerStatus.READY:
        raise HTTPException(409, "version not READY")
    await session.execute(PythonVersion.__table__.update().values(is_default=False))
    pv.is_default = True
    await session.commit()
    await session.refresh(pv)
    return PythonVersionRead.model_validate(pv)


@router.get(
    "/python-versions/{version_id}/log",
    dependencies=[Depends(require_perm("environment.read"))],
)
async def pyver_log(
    version_id: uuid.UUID, session: AsyncSession = Depends(get_session)
):
    pv = (
        await session.execute(
            select(PythonVersion).where(PythonVersion.id == version_id)
        )
    ).scalar_one_or_none()
    if pv is None or pv.build_log_path is None:
        raise HTTPException(404, "log not found")
    if not os.path.exists(pv.build_log_path):
        raise HTTPException(404, "log file missing on disk")
    return FileResponse(pv.build_log_path, media_type="text/plain")


@router.get(
    "/mirror-sources",
    response_model=list[MirrorRead],
    dependencies=[Depends(require_perm("environment.read"))],
)
async def list_mirrors(session: AsyncSession = Depends(get_session)):
    rows = await session.execute(
        select(MirrorSource).order_by(
            MirrorSource.is_builtin.desc(), MirrorSource.name
        )
    )
    return [MirrorRead.model_validate(m) for m in rows.scalars().all()]


@router.post(
    "/mirror-sources",
    response_model=MirrorRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_perm("environment.manage"))],
)
async def create_mirror(
    body: MirrorCreate, session: AsyncSession = Depends(get_session)
):
    if (
        await session.execute(
            select(MirrorSource).where(MirrorSource.name == body.name)
        )
    ).scalar_one_or_none():
        raise HTTPException(409, "mirror name already exists")
    if body.is_default:
        await session.execute(MirrorSource.__table__.update().values(is_default=False))
    m = MirrorSource(
        name=body.name, url=body.url, is_default=body.is_default, is_builtin=False
    )
    session.add(m)
    await session.commit()
    await session.refresh(m)
    return MirrorRead.model_validate(m)


@router.delete(
    "/mirror-sources/{mirror_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_perm("environment.manage"))],
)
async def delete_mirror(
    mirror_id: uuid.UUID, session: AsyncSession = Depends(get_session)
):
    m = (
        await session.execute(select(MirrorSource).where(MirrorSource.id == mirror_id))
    ).scalar_one_or_none()
    if m is None:
        raise HTTPException(404, "mirror not found")
    if m.is_builtin:
        raise HTTPException(409, "cannot delete builtin mirror")
    await session.delete(m)
    await session.commit()


router_envs = APIRouter(prefix="/environments", tags=["environments"])


@router_envs.get(
    "",
    response_model=PaginatedResponse,
)
async def list_environments(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_perm("environment.read")),
):
    visibility = env_visibility_clause(user)
    cq = select(func.count(Environment.id))
    q = select(Environment)
    if visibility is not None:
        cq = cq.where(visibility)
        q = q.where(visibility)
    total = (await session.execute(cq)).scalar() or 0
    skip = (page - 1) * page_size
    rows = await session.execute(
        q.order_by(Environment.created_at.desc()).offset(skip).limit(page_size)
    )
    items = [EnvironmentRead.model_validate(e) for e in rows.scalars().all()]
    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size,
    )


@router_envs.get(
    "/{env_id}",
    response_model=EnvironmentRead,
)
async def get_environment(
    env_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_perm("environment.read")),
):
    e = (
        await session.execute(select(Environment).where(Environment.id == env_id))
    ).scalar_one_or_none()
    if e is None or not await user_can_read_env(session, user, env_id):
        raise HTTPException(404, "environment not found")
    return EnvironmentRead.model_validate(e)


@router_envs.post(
    "",
    response_model=EnvironmentRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_env(
    body: EnvironmentCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_perm("environment.manage")),
):
    if (
        await session.execute(
            select(Environment).where(Environment.name == body.name)
        )
    ).scalar_one_or_none():
        raise HTTPException(409, "environment name already exists")
    e = Environment(
        name=body.name,
        description=body.description,
        node_id=body.node_id,
        python_version_id=body.python_version_id,
        mirror_id=body.mirror_id,
        requirements=body.requirements,
        tags=body.tags or [],
        owner_id=user.id,
        status=EnvStatus.CREATING,
    )
    session.add(e)
    await session.commit()
    await session.refresh(e)
    asyncio.create_task(create_environment(e.id))
    return EnvironmentRead.model_validate(e)


@router_envs.put(
    "/{env_id}",
    response_model=EnvironmentRead,
)
async def update_env(
    env_id: uuid.UUID,
    body: EnvironmentUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_perm("environment.manage")),
):
    e = (
        await session.execute(select(Environment).where(Environment.id == env_id))
    ).scalar_one_or_none()
    if e is None or not await user_can_write_env(session, user, env_id):
        raise HTTPException(404, "environment not found")
    for field, val in body.model_dump(exclude_unset=True).items():
        setattr(e, field, val)
    await session.commit()
    await session.refresh(e)
    return EnvironmentRead.model_validate(e)


@router_envs.post(
    "/{env_id}/rebuild",
    response_model=EnvironmentRead,
)
async def rebuild_env(
    env_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_perm("environment.manage")),
):
    e = (
        await session.execute(select(Environment).where(Environment.id == env_id))
    ).scalar_one_or_none()
    if e is None or not await user_can_write_env(session, user, env_id):
        raise HTTPException(404, "environment not found")
    e.status = EnvStatus.UPDATING
    e.error_msg = None
    await session.commit()
    asyncio.create_task(create_environment(e.id))
    await session.refresh(e)
    return EnvironmentRead.model_validate(e)


@router_envs.delete(
    "/{env_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_env(
    env_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_perm("environment.manage")),
):
    e = (
        await session.execute(select(Environment).where(Environment.id == env_id))
    ).scalar_one_or_none()
    if e is None:
        raise HTTPException(404, "environment not found")
    if not await user_owns_env(session, user, env_id):
        raise HTTPException(403, "only environment owner or superuser can delete")
    await session.delete(e)
    await session.commit()


@router_envs.get(
    "/{env_id}/log",
)
async def env_log(
    env_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_perm("environment.read")),
):
    if not await user_can_read_env(session, user, env_id):
        raise HTTPException(404, "log not found")
    e = (
        await session.execute(select(Environment).where(Environment.id == env_id))
    ).scalar_one_or_none()
    if e is None or e.install_log_path is None:
        raise HTTPException(404, "log not found")
    if not os.path.exists(e.install_log_path):
        raise HTTPException(404, "log file missing on disk")
    return FileResponse(e.install_log_path, media_type="text/plain")

@router_envs.get("/{env_id}/collaborators")
async def list_env_collaborators(
    env_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_perm("environment.read")),
):
    if not await user_can_read_env(session, user, env_id):
        raise HTTPException(404, "environment not found")
    rows = await session.execute(
        select(EnvironmentCollaborator, User)
        .join(User, EnvironmentCollaborator.user_id == User.id)
        .where(EnvironmentCollaborator.env_id == env_id)
        .order_by(EnvironmentCollaborator.created_at.asc())
    )
    return [
        {
            "user_id": str(u.id),
            "username": u.username,
            "full_name": u.full_name,
            "added_at": c.created_at,
        }
        for c, u in rows.all()
    ]


@router_envs.post("/{env_id}/collaborators", status_code=status.HTTP_201_CREATED)
async def add_env_collaborator(
    env_id: uuid.UUID,
    body: dict,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_perm("environment.manage")),
):
    if not await user_owns_env(session, user, env_id):
        raise HTTPException(403, "only environment owner or superuser can manage collaborators")
    target_user_id = body.get("user_id")
    if not target_user_id:
        raise HTTPException(400, "user_id required")
    target = (await session.execute(select(User).where(User.id == target_user_id))).scalar_one_or_none()
    if target is None:
        raise HTTPException(404, "user not found")
    existing = (
        await session.execute(
            select(EnvironmentCollaborator).where(
                EnvironmentCollaborator.env_id == env_id,
                EnvironmentCollaborator.user_id == target.id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return {"user_id": str(target.id), "username": target.username}
    session.add(EnvironmentCollaborator(env_id=env_id, user_id=target.id))
    await session.commit()
    return {"user_id": str(target.id), "username": target.username}


@router_envs.delete("/{env_id}/collaborators/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_env_collaborator(
    env_id: uuid.UUID,
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_perm("environment.manage")),
):
    if not await user_owns_env(session, user, env_id):
        raise HTTPException(403, "only environment owner or superuser can manage collaborators")
    row = (
        await session.execute(
            select(EnvironmentCollaborator).where(
                EnvironmentCollaborator.env_id == env_id,
                EnvironmentCollaborator.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if row is not None:
        await session.delete(row)
        await session.commit()

