"""Operations APIs: notifications, persistent files, SMTP, logs management."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt, encrypt
from app.core.database import get_session
from app.core.deps import require_perm
from app.core.notifier import emit_event
from app.core.persistent_files import persistent_files
from app.models.notification import (
    ChannelType,
    EventType,
    LogRetentionPolicy,
    NotificationChannel,
    NotificationEvent,
    NotificationRule,
    SmtpSettings,
)
from app.models.task import RunStatus, TaskRun

router = APIRouter(tags=["ops"])


# ===== Notifications =====


class ChannelCreate(BaseModel):
    type: ChannelType
    name: str = Field(max_length=128)
    config: dict
    is_enabled: bool = True
    template: str | None = None


class ChannelUpdate(BaseModel):
    name: str | None = None
    config: dict | None = None
    is_enabled: bool | None = None
    template: str | None = None


class ChannelRead(BaseModel):
    id: uuid.UUID
    type: ChannelType
    name: str
    is_enabled: bool
    has_secret: bool
    template: str | None
    created_at: datetime
    updated_at: datetime


class RuleCreate(BaseModel):
    channel_id: uuid.UUID
    event: EventType
    filter: dict | None = None


class RuleRead(BaseModel):
    id: uuid.UUID
    channel_id: uuid.UUID
    event: EventType
    filter: dict | None
    created_at: datetime


@router.get(
    "/notification-channels",
    response_model=list[ChannelRead],
    dependencies=[Depends(require_perm("settings.read"))],
)
async def list_channels(session: AsyncSession = Depends(get_session)):
    rows = (
        await session.execute(
            select(NotificationChannel).order_by(NotificationChannel.name)
        )
    ).scalars().all()
    return [
        ChannelRead(
            id=c.id,
            type=c.type,
            name=c.name,
            is_enabled=c.is_enabled,
            has_secret=bool(c.config_enc),
            template=c.template,
            created_at=c.created_at,
            updated_at=c.updated_at,
        )
        for c in rows
    ]


@router.post(
    "/notification-channels",
    response_model=ChannelRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_perm("settings.manage"))],
)
async def create_channel(
    body: ChannelCreate, session: AsyncSession = Depends(get_session)
):
    if (
        await session.execute(
            select(NotificationChannel).where(NotificationChannel.name == body.name)
        )
    ).scalar_one_or_none():
        raise HTTPException(409, "channel name already exists")
    c = NotificationChannel(
        type=body.type,
        name=body.name,
        config_enc=encrypt(json.dumps(body.config)) or "",
        is_enabled=body.is_enabled,
        template=body.template,
    )
    session.add(c)
    await session.commit()
    await session.refresh(c)
    return ChannelRead(
        id=c.id,
        type=c.type,
        name=c.name,
        is_enabled=c.is_enabled,
        has_secret=True,
        template=c.template,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


@router.put(
    "/notification-channels/{channel_id}",
    response_model=ChannelRead,
    dependencies=[Depends(require_perm("settings.manage"))],
)
async def update_channel(
    channel_id: uuid.UUID,
    body: ChannelUpdate,
    session: AsyncSession = Depends(get_session),
):
    c = (
        await session.execute(
            select(NotificationChannel).where(NotificationChannel.id == channel_id)
        )
    ).scalar_one_or_none()
    if c is None:
        raise HTTPException(404, "channel not found")
    if body.name is not None:
        c.name = body.name
    if body.is_enabled is not None:
        c.is_enabled = body.is_enabled
    if body.config is not None:
        c.config_enc = encrypt(json.dumps(body.config)) or ""
    if body.template is not None:
        # Empty string clears the override.
        c.template = body.template if body.template.strip() else None
    await session.commit()
    await session.refresh(c)
    return ChannelRead(
        id=c.id,
        type=c.type,
        name=c.name,
        is_enabled=c.is_enabled,
        has_secret=bool(c.config_enc),
        template=c.template,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


@router.delete(
    "/notification-channels/{channel_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_perm("settings.manage"))],
)
async def delete_channel(
    channel_id: uuid.UUID, session: AsyncSession = Depends(get_session)
):
    c = (
        await session.execute(
            select(NotificationChannel).where(NotificationChannel.id == channel_id)
        )
    ).scalar_one_or_none()
    if c is None:
        raise HTTPException(404, "channel not found")
    await session.delete(c)
    await session.commit()


@router.post(
    "/notification-channels/{channel_id}/test",
    dependencies=[Depends(require_perm("settings.manage"))],
)
async def test_channel(
    channel_id: uuid.UUID, session: AsyncSession = Depends(get_session)
):
    c = (
        await session.execute(
            select(NotificationChannel).where(NotificationChannel.id == channel_id)
        )
    ).scalar_one_or_none()
    if c is None:
        raise HTTPException(404, "channel not found")
    from app.core.notifier import _send_via

    try:
        await _send_via(c, "🔔 SpiderMan 测试通知")
    except Exception as e:
        raise HTTPException(400, f"send failed: {e}")
    return {"ok": True}


@router.get(
    "/notification-rules",
    response_model=list[RuleRead],
    dependencies=[Depends(require_perm("settings.read"))],
)
async def list_rules(session: AsyncSession = Depends(get_session)):
    rows = (
        await session.execute(
            select(NotificationRule).order_by(NotificationRule.created_at.desc())
        )
    ).scalars().all()
    return [
        RuleRead(
            id=r.id,
            channel_id=r.channel_id,
            event=r.event,
            filter=r.filter,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.post(
    "/notification-rules",
    response_model=RuleRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_perm("settings.manage"))],
)
async def create_rule(
    body: RuleCreate, session: AsyncSession = Depends(get_session)
):
    r = NotificationRule(
        channel_id=body.channel_id, event=body.event, filter=body.filter or {}
    )
    session.add(r)
    await session.commit()
    await session.refresh(r)
    return RuleRead(
        id=r.id,
        channel_id=r.channel_id,
        event=r.event,
        filter=r.filter,
        created_at=r.created_at,
    )


@router.delete(
    "/notification-rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_perm("settings.manage"))],
)
async def delete_rule(
    rule_id: uuid.UUID, session: AsyncSession = Depends(get_session)
):
    r = (
        await session.execute(
            select(NotificationRule).where(NotificationRule.id == rule_id)
        )
    ).scalar_one_or_none()
    if r is None:
        raise HTTPException(404, "rule not found")
    await session.delete(r)
    await session.commit()


# ===== SMTP Settings =====


class SmtpRead(BaseModel):
    host: str | None = None
    port: int = 587
    username: str | None = None
    from_addr: str | None = None
    use_tls: bool = True
    is_enabled: bool = False


class SmtpUpdate(BaseModel):
    host: str
    port: int = 587
    username: str | None = None
    password: str | None = None
    from_addr: str
    use_tls: bool = True
    is_enabled: bool = True


@router.get(
    "/smtp-settings",
    response_model=SmtpRead,
    dependencies=[Depends(require_perm("settings.read"))],
)
async def get_smtp(session: AsyncSession = Depends(get_session)):
    row = (
        await session.execute(
            select(SmtpSettings).order_by(SmtpSettings.created_at.desc()).limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        return SmtpRead()
    return SmtpRead(
        host=row.host,
        port=row.port,
        username=row.username,
        from_addr=row.from_addr,
        use_tls=row.use_tls,
        is_enabled=row.is_enabled,
    )


@router.put(
    "/smtp-settings",
    response_model=SmtpRead,
    dependencies=[Depends(require_perm("settings.manage"))],
)
async def update_smtp(
    body: SmtpUpdate, session: AsyncSession = Depends(get_session)
):
    row = (
        await session.execute(
            select(SmtpSettings).order_by(SmtpSettings.created_at.desc()).limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        row = SmtpSettings(
            host=body.host,
            port=body.port,
            username=body.username,
            password_enc=encrypt(body.password) if body.password else None,
            from_addr=body.from_addr,
            use_tls=body.use_tls,
            is_enabled=body.is_enabled,
        )
        session.add(row)
    else:
        row.host = body.host
        row.port = body.port
        row.username = body.username
        if body.password:
            row.password_enc = encrypt(body.password)
        row.from_addr = body.from_addr
        row.use_tls = body.use_tls
        row.is_enabled = body.is_enabled
    await session.commit()
    await session.refresh(row)
    return SmtpRead(
        host=row.host,
        port=row.port,
        username=row.username,
        from_addr=row.from_addr,
        use_tls=row.use_tls,
        is_enabled=row.is_enabled,
    )


# ===== Persistent Files =====


@router.get(
    "/files",
    dependencies=[Depends(require_perm("settings.read"))],
)
async def list_files(path: str = Query(default="")):
    return persistent_files.list_dir(path)


@router.post(
    "/files/folder",
    dependencies=[Depends(require_perm("settings.manage"))],
)
async def make_folder(path: str = Query(...)):
    try:
        persistent_files.make_dir(path)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@router.post(
    "/files/upload",
    dependencies=[Depends(require_perm("settings.manage"))],
)
async def upload_file(
    path: str = Query(default=""),
    file: UploadFile = File(...),
):
    try:
        rel = await persistent_files.save_upload(path, file)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"path": rel, "script_path": persistent_files.script_path(rel)}


@router.get(
    "/files/download",
    dependencies=[Depends(require_perm("settings.read"))],
)
async def download_file(path: str = Query(...)):
    try:
        target = persistent_files.open_for_download(path)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except FileNotFoundError:
        raise HTTPException(404, "file not found")
    return FileResponse(target, filename=target.name)


@router.delete(
    "/files",
    dependencies=[Depends(require_perm("settings.manage"))],
)
async def delete_file(path: str = Query(...)):
    try:
        persistent_files.delete(path)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except FileNotFoundError:
        raise HTTPException(404, "file not found")
    return {"ok": True}


# ===== Logs Management =====


LOG_ROOT = Path(os.environ.get("TASK_LOG_ROOT", "/tmp/spiderman/taskLogs"))


class LogFileEntry(BaseModel):
    run_id: uuid.UUID
    task_id: uuid.UUID | None = None
    task_name: str | None = None
    file_name: str
    size: int
    created_at: datetime


@router.get(
    "/logs",
    response_model=list[LogFileEntry],
    dependencies=[Depends(require_perm("task.read"))],
)
async def list_logs(
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
):
    rows = (
        await session.execute(
            select(TaskRun)
            .where(TaskRun.log_file_path.is_not(None))
            .order_by(desc(TaskRun.created_at))
            .limit(limit)
        )
    ).scalars().all()
    out: list[LogFileEntry] = []
    for r in rows:
        try:
            stat = os.stat(r.log_file_path) if r.log_file_path else None
            size = stat.st_size if stat else 0
        except OSError:
            size = 0
        out.append(
            LogFileEntry(
                run_id=r.id,
                task_id=r.task_id,
                task_name=None,
                file_name=Path(r.log_file_path).name if r.log_file_path else "",
                size=size,
                created_at=r.created_at,
            )
        )
    return out


@router.delete(
    "/logs/{run_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_perm("task.delete"))],
)
async def delete_log(
    run_id: uuid.UUID, session: AsyncSession = Depends(get_session)
):
    r = (
        await session.execute(select(TaskRun).where(TaskRun.id == run_id))
    ).scalar_one_or_none()
    if r is None:
        raise HTTPException(404, "run not found")
    if r.log_file_path and os.path.exists(r.log_file_path):
        os.unlink(r.log_file_path)
    r.log_file_path = None
    await session.commit()


class RetentionUpdate(BaseModel):
    days_to_keep: int = Field(ge=1, le=3650)
    is_enabled: bool = True


@router.get(
    "/logs/retention",
    dependencies=[Depends(require_perm("settings.read"))],
)
async def get_retention(session: AsyncSession = Depends(get_session)):
    p = (
        await session.execute(
            select(LogRetentionPolicy).order_by(LogRetentionPolicy.created_at.desc()).limit(1)
        )
    ).scalar_one_or_none()
    if p is None:
        return {"days_to_keep": 30, "is_enabled": False, "last_run_at": None}
    return {
        "days_to_keep": p.days_to_keep,
        "is_enabled": p.is_enabled,
        "last_run_at": p.last_run_at,
    }


@router.put(
    "/logs/retention",
    dependencies=[Depends(require_perm("settings.manage"))],
)
async def set_retention(
    body: RetentionUpdate, session: AsyncSession = Depends(get_session)
):
    p = (
        await session.execute(
            select(LogRetentionPolicy).order_by(LogRetentionPolicy.created_at.desc()).limit(1)
        )
    ).scalar_one_or_none()
    if p is None:
        p = LogRetentionPolicy(
            name="default",
            days_to_keep=body.days_to_keep,
            is_enabled=body.is_enabled,
        )
        session.add(p)
    else:
        p.days_to_keep = body.days_to_keep
        p.is_enabled = body.is_enabled
    await session.commit()
    return {
        "days_to_keep": p.days_to_keep,
        "is_enabled": p.is_enabled,
        "last_run_at": p.last_run_at,
    }


@router.post(
    "/logs/cleanup",
    dependencies=[Depends(require_perm("settings.manage"))],
)
async def cleanup_logs_now(session: AsyncSession = Depends(get_session)):
    p = (
        await session.execute(
            select(LogRetentionPolicy).order_by(LogRetentionPolicy.created_at.desc()).limit(1)
        )
    ).scalar_one_or_none()
    days = p.days_to_keep if p else 30
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        await session.execute(
            select(TaskRun).where(
                TaskRun.created_at < cutoff,
                TaskRun.log_file_path.is_not(None),
            )
        )
    ).scalars().all()
    deleted = 0
    for r in rows:
        if r.log_file_path and os.path.exists(r.log_file_path):
            try:
                os.unlink(r.log_file_path)
                deleted += 1
            except OSError:
                pass
        r.log_file_path = None
    if p is not None:
        p.last_run_at = datetime.now(timezone.utc)
    await session.commit()
    return {"deleted": deleted, "older_than_days": days}
