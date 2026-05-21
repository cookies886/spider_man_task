from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.rate_limit import RateLimitExceeded, check_and_incr, reset
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.models.user import PageACL, Permission, RolePermission, User, UserRole
from app.schemas.auth import LoginRequest, Token, TokenRefresh

router = APIRouter(prefix="/auth", tags=["auth"])

# 5 failures per 15 min, double-keyed by IP and username so neither dimension
# alone can be brute-forced.
_LOGIN_LIMIT = 5
_LOGIN_WINDOW = 900


async def _user_permissions(session: AsyncSession, user: User) -> list[str]:
    if user.is_superuser:
        rows = await session.execute(select(Permission.code))
        return list(rows.scalars().all())
    rows = await session.execute(
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(UserRole.user_id == user.id)
        .distinct()
    )
    return list(rows.scalars().all())


async def _user_pages(session: AsyncSession, user: User) -> list[str]:
    if user.is_superuser:
        from app.core.seed import PAGE_KEYS

        return list(PAGE_KEYS)
    rows = await session.execute(
        select(PageACL.page_key).where(PageACL.user_id == user.id)
    )
    return list(rows.scalars().all())


async def _build_claims(session: AsyncSession, user: User) -> dict:
    perms = await _user_permissions(session, user)
    pages = await _user_pages(session, user)
    return {
        "uid": str(user.id),
        "superuser": user.is_superuser,
        "must_change_password": user.must_change_password,
        "perms": sorted(perms),
        "pages": sorted(pages),
    }


@router.post("/login", response_model=Token)
async def login(
    body: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    client_ip = (
        request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or (request.client.host if request.client else "unknown")
    )
    ip_key = f"rl:login:ip:{client_ip}"
    user_key = f"rl:login:user:{body.username}"

    try:
        await check_and_incr(ip_key, _LOGIN_LIMIT, _LOGIN_WINDOW)
        await check_and_incr(user_key, _LOGIN_LIMIT, _LOGIN_WINDOW)
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"登录尝试过于频繁，请 {exc.retry_after} 秒后再试",
            headers={"Retry-After": str(exc.retry_after)},
        )

    row = await session.execute(select(User).where(User.username == body.username))
    user = row.scalar_one_or_none()
    if (
        user is None
        or not user.is_active
        or not verify_password(body.password, user.password_hash)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    # Success: clear both counters so a legitimate user with a flubbed
    # password earlier doesn't stay throttled.
    await reset(ip_key)
    await reset(user_key)

    user.last_login_at = datetime.now(timezone.utc)
    await session.commit()

    claims = await _build_claims(session, user)
    return Token(
        access_token=create_access_token(subject=user.username, extra=claims),
        refresh_token=create_refresh_token(subject=user.username),
    )


@router.post("/refresh", response_model=Token)
async def refresh_token(
    body: TokenRefresh, session: AsyncSession = Depends(get_session)
):
    payload = decode_token(body.refresh_token)
    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    subject = payload["sub"]
    row = await session.execute(select(User).where(User.username == subject))
    user = row.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(401, "User not found or inactive")
    claims = await _build_claims(session, user)
    return Token(
        access_token=create_access_token(subject=user.username, extra=claims),
        refresh_token=create_refresh_token(subject=user.username),
    )
