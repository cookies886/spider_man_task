from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.deps import get_current_user
from app.models.user import Permission, Role, RolePermission
from app.schemas.user import RoleRead

router = APIRouter(
    prefix="/roles",
    tags=["roles"],
    dependencies=[Depends(get_current_user)],
)


@router.get("", response_model=list[RoleRead])
async def list_roles(session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(Role).order_by(Role.code))).scalars().all()
    out = []
    for r in rows:
        perm_codes = (
            await session.execute(
                select(Permission.code)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .where(RolePermission.role_id == r.id)
            )
        ).scalars().all()
        out.append(
            RoleRead.model_validate(
                {
                    "id": r.id,
                    "created_at": r.created_at,
                    "updated_at": r.updated_at,
                    "code": r.code,
                    "name": r.name,
                    "description": r.description,
                    "is_system": r.is_system,
                    "permission_codes": list(perm_codes),
                }
            )
        )
    return out
