import pytest
from sqlalchemy import select

from app.core.database import async_session
from app.core.seed import ensure_seed_data
from app.models.user import Permission, Role, User


@pytest.mark.asyncio
async def test_seed_is_idempotent():
    await ensure_seed_data()
    await ensure_seed_data()
    async with async_session() as s:
        perms = (await s.execute(select(Permission))).scalars().all()
        roles = (await s.execute(select(Role))).scalars().all()
        admin = (
            await s.execute(select(User).where(User.username == "admin"))
        ).scalar_one()
        assert len(perms) >= 20
        assert {r.code for r in roles} >= {"admin", "operator", "viewer"}
        assert admin.is_superuser is True
