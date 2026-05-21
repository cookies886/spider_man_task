"""Project management API.

Slice 3 covers:
- POST /projects (zip upload OR git config)
- GET /projects (list)
- GET /projects/{id} (detail)
- PUT /projects/{id} (metadata update)
- DELETE /projects/{id}
- GET /projects/{id}/files?path= (tree at path)
- GET /projects/{id}/file?path= (read text)
- PUT /projects/{id}/file?path= (write text)
- DELETE /projects/{id}/file?path=
- POST /projects/{id}/git/sync (manual pull)
- GET /projects/{id}/zip — internal worker fetch (api-key auth)
"""
from __future__ import annotations

import json
import os
import uuid
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import (
    project_visibility_clause,
    user_can_read_project,
    user_can_write_project,
    user_owns_project,
)
from app.core.audit import log_action
from app.core.database import get_session
from app.core.deps import get_current_user, require_perm
from app.core.file_manager import file_manager
from app.core.git_sync import git_sync_service
from app.models.project import (
    DistributionStatus,
    GitRepo,
    Project,
    ProjectCollaborator,
    ProjectDistribution,
    SourceType,
)
from app.models.user import User
from app.models.worker import Worker
from app.schemas.common import PaginatedResponse
from app.schemas.project import (
    DistributionRead,
    GitRepoRead,
    ProjectCreate,
    ProjectDetail,
    ProjectFileEntry,
    ProjectRead,
    ProjectUpdate,
    GitSyncResult,
    FileWriteBody,
)

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get(
    "",
    response_model=PaginatedResponse,
)
async def list_projects(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_perm("project.read")),
):
    q = select(Project)
    cq = select(func.count(Project.id))
    if search:
        q = q.where(Project.name.ilike(f"%{search}%"))
        cq = cq.where(Project.name.ilike(f"%{search}%"))
    visibility = project_visibility_clause(user)
    if visibility is not None:
        q = q.where(visibility)
        cq = cq.where(visibility)
    total = (await session.execute(cq)).scalar() or 0
    skip = (page - 1) * page_size
    rows = await session.execute(
        q.order_by(Project.created_at.desc()).offset(skip).limit(page_size)
    )
    items = [ProjectRead.model_validate(p) for p in rows.scalars().all()]
    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size,
    )


async def _hydrate_detail(session: AsyncSession, project: Project) -> ProjectDetail:
    base = ProjectRead.model_validate(project).model_dump()
    git = (
        await session.execute(select(GitRepo).where(GitRepo.project_id == project.id))
    ).scalar_one_or_none()
    git_read = (
        GitRepoRead(
            url=git.url,
            branch=git.branch,
            username=git.username,
            sync_interval_seconds=git.sync_interval_seconds,
            last_sync_at=git.last_sync_at,
            last_commit=git.last_commit,
            last_error=git.last_error,
        )
        if git
        else None
    )
    dists = (
        await session.execute(
            select(ProjectDistribution).where(
                ProjectDistribution.project_id == project.id
            )
        )
    ).scalars().all()
    return ProjectDetail(
        **base,
        git=git_read,
        distributions=[
            DistributionRead(
                node_id=d.node_id,
                status=d.status,
                last_synced_at=d.last_synced_at,
                current_hash=d.current_hash,
                last_error=d.last_error,
            )
            for d in dists
        ],
    )


@router.get(
    "/{project_id}",
    response_model=ProjectDetail,
)
async def get_project_detail(
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_perm("project.read")),
):
    proj = (
        await session.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()
    if not proj:
        raise HTTPException(404, "project not found")
    if not await user_can_read_project(session, user, project_id):
        raise HTTPException(404, "project not found")
    return await _hydrate_detail(session, proj)


@router.post(
    "",
    response_model=ProjectDetail,
    status_code=status.HTTP_201_CREATED,
)
async def create_project(
    request: Request,
    body: Annotated[str | None, Form()] = None,
    file: UploadFile | None = File(default=None),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_perm("project.create")),
):
    """Create a project. Two modes:

    - **ZIP**: send `multipart/form-data` with `body` (JSON ProjectCreate, source_type=zip)
      and `file` (the .zip).
    - **Git**: send `application/json` with ProjectCreate (source_type=git, git=...).
    """
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("multipart/"):
        if not body:
            raise HTTPException(400, "missing body field")
        try:
            payload = ProjectCreate.model_validate_json(body)
        except Exception as e:
            raise HTTPException(400, f"invalid body json: {e}")
    else:
        payload = ProjectCreate.model_validate(await request.json())

    if payload.source_type == SourceType.ZIP and file is None:
        raise HTTPException(400, "zip project requires file upload")
    if payload.source_type == SourceType.GIT and payload.git is None:
        raise HTTPException(400, "git project requires git config")

    # Name uniqueness
    exists = (
        await session.execute(select(Project).where(Project.name == payload.name))
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(409, "project name already exists")

    proj = Project(
        name=payload.name,
        description=payload.description,
        source_type=payload.source_type,
        work_path=payload.work_path,
        owner_id=user.id,
        default_node_id=payload.default_node_id,
        default_env_id=payload.default_env_id,
        tags=payload.tags or [],
    )
    session.add(proj)
    await session.flush()

    if payload.source_type == SourceType.ZIP:
        inferred = await file_manager.extract_zip(proj.id, file)
        if proj.work_path == "/" and inferred != "/":
            proj.work_path = inferred
        proj.current_hash = file_manager.repackage(proj.id)
    else:
        gc = payload.git
        repo = GitRepo(
            project_id=proj.id,
            url=gc.url,
            branch=gc.branch,
            username=gc.username,
            password_enc=gc.password,  # TODO: Fernet, slice 7
            sync_interval_seconds=gc.sync_interval_seconds,
        )
        session.add(repo)
        await session.commit()
        await session.refresh(proj)
        try:
            await git_sync_service.sync(session, proj.id)
        except RuntimeError as e:
            raise HTTPException(400, f"initial git sync failed: {e}")

        # Register auto-pull job if interval is set
        if gc.sync_interval_seconds and gc.sync_interval_seconds > 0:
            from app.core.scheduler import scheduler_service

            scheduler_service.register_git_sync(proj.id, gc.sync_interval_seconds)

        await session.refresh(proj)
        return await _hydrate_detail(session, proj)

    await session.commit()
    await session.refresh(proj)
    return await _hydrate_detail(session, proj)


@router.put(
    "/{project_id}",
    response_model=ProjectDetail,
)
async def update_project(
    project_id: uuid.UUID,
    body: ProjectUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_perm("project.update")),
):
    if not await user_can_write_project(session, user, project_id):
        raise HTTPException(404, "project not found")
    proj = (
        await session.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()
    if not proj:
        raise HTTPException(404, "project not found")
    for field in ("description", "work_path", "default_node_id", "default_env_id"):
        v = getattr(body, field)
        if v is not None:
            setattr(proj, field, v)
    if body.tags is not None:
        proj.tags = body.tags
    await session.commit()
    await session.refresh(proj)
    return await _hydrate_detail(session, proj)


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_project(
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_perm("project.delete")),
):
    if not await user_owns_project(session, user, project_id):
        raise HTTPException(403, "only project owner or superuser can delete")
    proj = (
        await session.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()
    if not proj:
        raise HTTPException(404, "project not found")
    # Unregister auto git-pull job if any
    from app.core.scheduler import scheduler_service
    scheduler_service.unregister_git_sync(project_id)
    snapshot = {"id": str(proj.id), "name": proj.name, "source_type": str(proj.source_type)}
    await log_action(
        session, user, "project.delete",
        target_type="project", target_id=str(project_id),
        before=snapshot,
    )
    await session.delete(proj)
    await session.commit()
    file_manager.remove_workspace(project_id)


# -- Files --


@router.get(
    "/{project_id}/files",
    response_model=list[ProjectFileEntry],
)
async def list_files(
    project_id: uuid.UUID,
    path: str = Query(default=""),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_perm("project.read")),
):
    if not await user_can_read_project(session, user, project_id):
        raise HTTPException(404, "project not found")
    entries = file_manager.list_dir(project_id, path)
    return [
        ProjectFileEntry(
            name=e.name, path=e.path, is_dir=e.is_dir, size=e.size, mtime=e.mtime
        )
        for e in entries
    ]


@router.get(
    "/{project_id}/file",
)
async def read_file(
    project_id: uuid.UUID,
    path: str = Query(...),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_perm("project.read")),
):
    if not await user_can_read_project(session, user, project_id):
        raise HTTPException(404, "project not found")
    try:
        content = file_manager.read_file(project_id, path)
    except FileNotFoundError:
        raise HTTPException(404, "file not found")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"path": path, "content": content}


@router.put(
    "/{project_id}/file",
)
async def write_file(
    project_id: uuid.UUID,
    body: FileWriteBody,
    path: str = Query(...),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_perm("project.update")),
):
    if not await user_can_write_project(session, user, project_id):
        raise HTTPException(404, "project not found")
    try:
        file_manager.write_file(project_id, path, body.content)
    except ValueError as e:
        raise HTTPException(400, str(e))

    new_hash = file_manager.repackage(project_id)
    proj = (
        await session.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()
    if proj is None:
        raise HTTPException(404, "project not found")
    if proj.current_hash != new_hash:
        proj.current_hash = new_hash
        # mark all distributions stale
        await session.execute(
            ProjectDistribution.__table__.update()
            .where(ProjectDistribution.project_id == project_id)
            .values(status=DistributionStatus.STALE)
        )
        await session.commit()
    return {"path": path, "hash": new_hash}


@router.delete(
    "/{project_id}/file",
)
async def delete_file(
    project_id: uuid.UUID,
    path: str = Query(...),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_perm("project.update")),
):
    if not await user_can_write_project(session, user, project_id):
        raise HTTPException(404, "project not found")
    try:
        file_manager.delete_file(project_id, path)
    except ValueError as e:
        raise HTTPException(400, str(e))
    new_hash = file_manager.repackage(project_id)
    proj = (
        await session.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()
    if proj and proj.current_hash != new_hash:
        proj.current_hash = new_hash
        await session.execute(
            ProjectDistribution.__table__.update()
            .where(ProjectDistribution.project_id == project_id)
            .values(status=DistributionStatus.STALE)
        )
        await session.commit()
    return {"path": path, "hash": new_hash}


# -- Git --


@router.post(
    "/{project_id}/git/sync",
    response_model=GitSyncResult,
)
async def manual_git_sync(
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_perm("project.update")),
):
    if not await user_can_write_project(session, user, project_id):
        raise HTTPException(404, "project not found")
    proj = (
        await session.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()
    if proj is None:
        raise HTTPException(404, "project not found")
    if proj.source_type != SourceType.GIT:
        raise HTTPException(400, "not a git project")
    try:
        result = await git_sync_service.sync(session, project_id)
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    return GitSyncResult(
        last_commit=result.last_commit,
        last_sync_at=result.last_sync_at,
        files_changed=result.files_changed,
    )


# -- Collaborators --


@router.get("/{project_id}/collaborators")
async def list_collaborators(
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_perm("project.read")),
):
    if not await user_can_read_project(session, user, project_id):
        raise HTTPException(404, "project not found")
    rows = await session.execute(
        select(ProjectCollaborator, User)
        .join(User, ProjectCollaborator.user_id == User.id)
        .where(ProjectCollaborator.project_id == project_id)
        .order_by(ProjectCollaborator.created_at.asc())
    )
    items = []
    for c, u in rows.all():
        items.append(
            {
                "user_id": str(u.id),
                "username": u.username,
                "full_name": u.full_name,
                "added_at": c.created_at,
            }
        )
    return items


@router.post(
    "/{project_id}/collaborators", status_code=status.HTTP_201_CREATED
)
async def add_collaborator(
    project_id: uuid.UUID,
    body: dict,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_perm("project.update")),
):
    if not await user_owns_project(session, user, project_id):
        raise HTTPException(403, "only project owner or superuser can manage collaborators")
    target_user_id = body.get("user_id")
    if not target_user_id:
        raise HTTPException(400, "user_id required")
    target = (
        await session.execute(select(User).where(User.id == target_user_id))
    ).scalar_one_or_none()
    if target is None:
        raise HTTPException(404, "user not found")
    existing = (
        await session.execute(
            select(ProjectCollaborator).where(
                ProjectCollaborator.project_id == project_id,
                ProjectCollaborator.user_id == target.id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return {"user_id": str(target.id), "username": target.username}
    session.add(
        ProjectCollaborator(project_id=project_id, user_id=target.id)
    )
    await session.commit()
    return {"user_id": str(target.id), "username": target.username}


@router.delete(
    "/{project_id}/collaborators/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_collaborator(
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_perm("project.update")),
):
    if not await user_owns_project(session, user, project_id):
        raise HTTPException(403, "only project owner or superuser can manage collaborators")
    row = (
        await session.execute(
            select(ProjectCollaborator).where(
                ProjectCollaborator.project_id == project_id,
                ProjectCollaborator.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if row is not None:
        await session.delete(row)
        await session.commit()


# -- Internal worker fetch --


@router.get("/{project_id}/zip")
async def internal_zip_fetch(
    project_id: uuid.UUID,
    node_token: str = Query(..., alias="token"),
    node_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
):
    """Worker fetches the project's packaged zip. Authenticated via node api_key."""
    import bcrypt

    row = await session.execute(select(Worker).where(Worker.node_id == node_id))
    worker = row.scalar_one_or_none()
    if worker is None or not bcrypt.checkpw(
        node_token.encode(), worker.api_key_hash.encode()
    ):
        raise HTTPException(401, "invalid node credentials")
    zp = file_manager.zip_path(project_id)
    if not zp.exists():
        raise HTTPException(404, "no zip available")
    return FileResponse(
        zp,
        filename=f"{project_id}.zip",
        media_type="application/zip",
        headers={"X-Project-Hash": (
            (await session.execute(select(Project.current_hash).where(Project.id == project_id))).scalar() or ""
        )},
    )
