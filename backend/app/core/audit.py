"""Audit helper. Best-effort writes — never let logging break the actual operation."""
from __future__ import annotations

import logging

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.request_id import request_id_var
from app.models.audit import AuditLog
from app.models.user import User

logger = logging.getLogger(__name__)


async def log_action(
    session: AsyncSession,
    user: User | None,
    action: str,
    target_type: str | None = None,
    target_id: str | None = None,
    *,
    before: dict | None = None,
    after: dict | None = None,
    request: Request | None = None,
) -> None:
    """Write one audit row. Caller is responsible for committing the session."""
    try:
        ip = None
        ua = None
        if request is not None:
            ip = (
                request.headers.get("x-forwarded-for", "").split(",")[0].strip()
                or (request.client.host if request.client else None)
            )
            ua = request.headers.get("user-agent")
        entry = AuditLog(
            actor_id=user.id if user else None,
            actor_name=user.username if user else None,
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id else None,
            before=before,
            after=after,
            ip=ip,
            user_agent=ua[:256] if ua else None,
            request_id=request_id_var.get(),
        )
        session.add(entry)
    except Exception:
        logger.exception("audit log_action failed for %s", action)
