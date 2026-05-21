from fastapi import APIRouter

from app.api.alerts import router as alerts_router
from app.api.audit import router as audit_router
from app.api.auth import router as auth_router
from app.api.dashboard import router as dashboard_router
from app.api.env_vars import router as env_vars_router
from app.api.environments import (
    router as envs_top_router,
    router_envs as environments_router,
)
from app.api.me import router as me_router
from app.api.ops import router as ops_router
from app.api.projects import router as projects_router
from app.api.roles import router as roles_router
from app.api.tasks import router as tasks_router
from app.api.users import router as users_router
from app.api.worker_groups import router as worker_groups_router
from app.api.workers import router as workers_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
api_router.include_router(projects_router)
api_router.include_router(tasks_router)
api_router.include_router(workers_router)
api_router.include_router(worker_groups_router)
api_router.include_router(environments_router)
api_router.include_router(envs_top_router)
api_router.include_router(env_vars_router)
api_router.include_router(alerts_router)
api_router.include_router(audit_router)
api_router.include_router(dashboard_router)
api_router.include_router(me_router)
api_router.include_router(users_router)
api_router.include_router(roles_router)
api_router.include_router(ops_router)
