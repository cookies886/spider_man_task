"""Read-only audit log endpoint."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.deps import get_current_user
from app.models.audit import AuditLog
from app.models.user import User

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("")
async def list_audit_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    action: str | None = None,
    actor_id: uuid.UUID | None = None,
    target_id: str | None = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """List audit logs. Superuser only — sensitive data."""
    if not user.is_superuser:
        raise HTTPException(403, "audit log requires superuser")
    q = select(AuditLog)
    cq = select(func.count(AuditLog.id))
    if action:
        q = q.where(AuditLog.action.like(f"{action}%"))
        cq = cq.where(AuditLog.action.like(f"{action}%"))
    if actor_id:
        q = q.where(AuditLog.actor_id == actor_id)
        cq = cq.where(AuditLog.actor_id == actor_id)
    if target_id:
        q = q.where(AuditLog.target_id == target_id)
        cq = cq.where(AuditLog.target_id == target_id)
    total = (await session.execute(cq)).scalar() or 0
    rows = (
        await session.execute(
            q.order_by(desc(AuditLog.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return {
        "total": total,
        "page": page,
        "items": [
            {
                "id": str(r.id),
                "actor_id": str(r.actor_id) if r.actor_id else None,
                "actor_name": r.actor_name,
                "action": r.action,
                "target_type": r.target_type,
                "target_id": r.target_id,
                "before": r.before,
                "after": r.after,
                "ip": r.ip,
                "user_agent": r.user_agent,
                "request_id": r.request_id,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ],
    }
