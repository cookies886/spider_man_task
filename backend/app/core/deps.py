import uuid

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.security import decode_token
from app.models.user import User

bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    token = credentials.credentials
    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    uid = payload.get("uid")
    if not uid:
        raise HTTPException(401, "Invalid token (missing uid)")
    try:
        uid_uuid = uuid.UUID(uid)
    except (TypeError, ValueError):
        raise HTTPException(401, "Invalid token (bad uid)")
    row = await session.execute(select(User).where(User.id == uid_uuid))
    user = row.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(401, "User not found or inactive")
    user.__claims__ = payload
    return user


def require_perm(code: str):
    async def _dep(user: User = Depends(get_current_user)) -> User:
        if user.is_superuser:
            return user
        claims = getattr(user, "__claims__", {}) or {}
        perms = claims.get("perms") or []
        if code not in perms:
            raise HTTPException(403, f"missing permission: {code}")
        return user

    return _dep


def require_superuser():
    async def _dep(user: User = Depends(get_current_user)) -> User:
        if not user.is_superuser:
            raise HTTPException(403, "superuser only")
        return user

    return _dep
