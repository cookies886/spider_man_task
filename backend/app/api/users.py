import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.deps import require_perm, require_superuser
from app.core.security import hash_password
from app.models.user import PageACL, Role, User, UserRole
from app.schemas.common import PaginatedResponse
from app.schemas.user import UserCreate, UserRead, UserUpdate

router = APIRouter(
    prefix="/users",
    tags=["users"],
    dependencies=[Depends(require_superuser())],
)


async def _hydrate(session: AsyncSession, user: User) -> UserRead:
    role_codes = (
        await session.execute(
            select(Role.code)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user.id)
        )
    ).scalars().all()
    pages = (
        await session.execute(
            select(PageACL.page_key).where(PageACL.user_id == user.id)
        )
    ).scalars().all()
    return UserRead.model_validate(
        {
            "id": user.id,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "is_active": user.is_active,
            "is_superuser": user.is_superuser,
            "must_change_password": user.must_change_password,
            "last_login_at": user.last_login_at,
            "role_codes": list(role_codes),
            "page_acls": list(pages),
        }
    )


@router.get("", response_model=PaginatedResponse)
async def list_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    total = (await session.execute(select(func.count(User.id)))).scalar() or 0
    skip = (page - 1) * page_size
    rows = await session.execute(
        select(User).order_by(User.created_at.desc()).offset(skip).limit(page_size)
    )
    items = [await _hydrate(session, u) for u in rows.scalars().all()]
    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size,
    )


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(body: UserCreate, session: AsyncSession = Depends(get_session)):
    if (
        await session.execute(select(User).where(User.username == body.username))
    ).scalar_one_or_none():
        raise HTTPException(409, "username already exists")
    u = User(
        username=body.username,
        password_hash=hash_password(body.password),
        email=body.email,
        full_name=body.full_name,
        is_active=body.is_active,
        must_change_password=True,
    )
    session.add(u)
    await session.flush()
    if body.role_codes:
        roles = (
            await session.execute(select(Role).where(Role.code.in_(body.role_codes)))
        ).scalars().all()
        for r in roles:
            session.add(UserRole(user_id=u.id, role_id=r.id))
    for p in body.page_acls:
        session.add(PageACL(user_id=u.id, page_key=p))
    await session.commit()
    await session.refresh(u)
    return await _hydrate(session, u)


@router.put("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    session: AsyncSession = Depends(get_session),
):
    u = (
        await session.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if u is None:
        raise HTTPException(404, "user not found")
    if body.email is not None:
        u.email = body.email
    if body.full_name is not None:
        u.full_name = body.full_name
    if body.is_active is not None:
        u.is_active = body.is_active
    if body.role_codes is not None:
        await session.execute(
            UserRole.__table__.delete().where(UserRole.user_id == u.id)
        )
        roles = (
            await session.execute(select(Role).where(Role.code.in_(body.role_codes)))
        ).scalars().all()
        for r in roles:
            session.add(UserRole(user_id=u.id, role_id=r.id))
    if body.page_acls is not None:
        await session.execute(
            PageACL.__table__.delete().where(PageACL.user_id == u.id)
        )
        for p in body.page_acls:
            session.add(PageACL(user_id=u.id, page_key=p))
    await session.commit()
    await session.refresh(u)
    return await _hydrate(session, u)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    actor: User = Depends(require_perm("user.manage")),
):
    u = (
        await session.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if u is None:
        raise HTTPException(404, "user not found")
    if u.is_superuser:
        raise HTTPException(409, "cannot delete superuser")
    from app.core.audit import log_action
    await log_action(
        session, actor, "user.delete",
        target_type="user", target_id=str(user_id),
        before={"username": u.username, "is_active": u.is_active},
    )
    await session.delete(u)
    await session.commit()


@router.post("/{user_id}/reset-password")
async def reset_password(
    user_id: uuid.UUID, session: AsyncSession = Depends(get_session)
):
    u = (
        await session.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if u is None:
        raise HTTPException(404, "user not found")
    new_pw = secrets.token_urlsafe(12)
    u.password_hash = hash_password(new_pw)
    u.must_change_password = True
    await session.commit()
    return {"new_password": new_pw}
