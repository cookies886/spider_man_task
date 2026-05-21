"""Idempotent seeding of system roles, permissions, and the admin user."""
from __future__ import annotations

import logging

from sqlalchemy import select

from app.core.config import settings
from app.core.database import async_session
from app.core.security import hash_password
from app.models.environment import MirrorSource
from app.models.user import (
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
)

logger = logging.getLogger(__name__)


PAGE_KEYS = [
    "dashboard",
    "projects",
    "tasks",
    "workers",
    "worker-groups",
    "environments",
    "python-versions",
    "mirror-sources",
    "env-vars",
    "logs",
    "files",
    "notifications",
    "users",
    "settings",
    "audit",
]

PERMISSION_CODES = [
    # Project
    "project.read",
    "project.create",
    "project.update",
    "project.delete",
    # Task
    "task.read",
    "task.create",
    "task.update",
    "task.delete",
    "task.execute",
    # Worker
    "worker.read",
    "worker.manage",
    # Worker group
    "worker_group.read",
    "worker_group.manage",
    # Schedule
    "schedule.read",
    "schedule.manage",
    # Environment
    "environment.read",
    "environment.manage",
    # Env var
    "env_var.read",
    "env_var.manage",
    # User
    "user.read",
    "user.manage",
    # System
    "settings.read",
    "settings.manage",
]

BUILTIN_MIRRORS = [
    {"name": "PyPI 官方", "url": "https://pypi.org/simple/", "is_default": False},
    {"name": "阿里云", "url": "https://mirrors.aliyun.com/pypi/simple/", "is_default": True},
    {"name": "清华大学", "url": "https://pypi.tuna.tsinghua.edu.cn/simple/", "is_default": False},
    {"name": "中科大", "url": "https://pypi.mirrors.ustc.edu.cn/simple/", "is_default": False},
    {"name": "华为云", "url": "https://repo.huaweicloud.com/repository/pypi/simple/", "is_default": False},
    {"name": "腾讯云", "url": "https://mirrors.cloud.tencent.com/pypi/simple/", "is_default": False},
]


SYSTEM_ROLES = {
    "admin": {
        "name": "管理员",
        "description": "全部权限",
        "permissions": "*",
    },
    "operator": {
        "name": "操作员",
        "description": "可创建/管理任务和项目，不可管理用户/系统设置",
        "permissions": [
            "project.read",
            "project.create",
            "project.update",
            "task.read",
            "task.create",
            "task.update",
            "task.execute",
            "worker.read",
            "worker_group.read",
            "worker_group.manage",
            "schedule.read",
            "schedule.manage",
            "environment.read",
            "environment.manage",
            "env_var.read",
        ],
    },
    "viewer": {
        "name": "查看者",
        "description": "只读",
        "permissions": [
            "project.read",
            "task.read",
            "worker.read",
            "worker_group.read",
            "schedule.read",
            "environment.read",
            "env_var.read",
        ],
    },
}


async def ensure_seed_data() -> None:
    async with async_session() as s:
        existing_perms = {
            row.code: row for row in (await s.execute(select(Permission))).scalars()
        }
        for code in PERMISSION_CODES:
            if code not in existing_perms:
                s.add(Permission(code=code))
        await s.flush()

        existing_perms = {
            row.code: row for row in (await s.execute(select(Permission))).scalars()
        }

        existing_roles = {
            row.code: row for row in (await s.execute(select(Role))).scalars()
        }
        for code, meta in SYSTEM_ROLES.items():
            if code in existing_roles:
                continue
            s.add(
                Role(
                    code=code,
                    name=meta["name"],
                    description=meta["description"],
                    is_system=True,
                )
            )
        await s.flush()
        existing_roles = {
            row.code: row for row in (await s.execute(select(Role))).scalars()
        }

        existing_links = {
            (rp.role_id, rp.permission_id)
            for rp in (await s.execute(select(RolePermission))).scalars()
        }
        for code, meta in SYSTEM_ROLES.items():
            role = existing_roles[code]
            wanted = (
                list(existing_perms.values())
                if meta["permissions"] == "*"
                else [existing_perms[c] for c in meta["permissions"]]
            )
            for perm in wanted:
                key = (role.id, perm.id)
                if key not in existing_links:
                    s.add(RolePermission(role_id=role.id, permission_id=perm.id))

        admin_username = settings.admin_username
        admin = (
            await s.execute(select(User).where(User.username == admin_username))
        ).scalar_one_or_none()
        if admin is None:
            admin = User(
                username=admin_username,
                password_hash=hash_password(settings.admin_password),
                full_name="Administrator",
                is_active=True,
                is_superuser=True,
                must_change_password=True,
            )
            s.add(admin)
            await s.flush()
            s.add(UserRole(user_id=admin.id, role_id=existing_roles["admin"].id))

        existing_mirrors = {
            m.name: m for m in (await s.execute(select(MirrorSource))).scalars()
        }
        for cfg in BUILTIN_MIRRORS:
            if cfg["name"] not in existing_mirrors:
                s.add(
                    MirrorSource(
                        name=cfg["name"],
                        url=cfg["url"],
                        is_default=cfg["is_default"],
                        is_builtin=True,
                    )
                )

        await s.commit()
        logger.info(
            "seed: %d perms, %d roles, %d mirrors ensured",
            len(PERMISSION_CODES),
            len(SYSTEM_ROLES),
            len(BUILTIN_MIRRORS),
        )
