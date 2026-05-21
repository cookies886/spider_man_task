from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.deps import get_current_user
from app.core.security import hash_password, verify_password
from app.models.user import User
from app.schemas.user import MeResponse, PasswordChange

router = APIRouter(tags=["me"])


@router.get("/me", response_model=MeResponse)
async def get_me(user: User = Depends(get_current_user)):
    claims = getattr(user, "__claims__", {}) or {}
    return MeResponse(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        email=user.email,
        is_superuser=user.is_superuser,
        must_change_password=user.must_change_password,
        permissions=claims.get("perms", []),
        page_acls=claims.get("pages", []),
        last_login_at=user.last_login_at,
    )


@router.post("/me/change-password", status_code=204)
async def change_password(
    body: PasswordChange,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if not verify_password(body.old_password, user.password_hash):
        raise HTTPException(400, "old password incorrect")
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    session.add(user)
    await session.commit()
