import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.api import api_router
from app.api.metrics_route import router as metrics_router
from app.core.config import settings
from app.core.database import async_session
from app.core.metrics import http_metrics_middleware
from app.core.redis import pool as redis_pool
from app.core.request_id import request_id_middleware
from app.core.scheduler import scheduler_service
from app.core.seed import ensure_seed_data
from app.models.worker import Worker, WorkerStatus, WorkerType
from app.ws import ws_router


async def _offline_sweep():
    """Mark workers offline if their last heartbeat is older than 60 seconds."""
    while True:
        try:
            await asyncio.sleep(30)
            cutoff = datetime.now(timezone.utc) - timedelta(seconds=60)
            async with async_session() as s:
                rows = await s.execute(
                    select(Worker).where(
                        Worker.status == WorkerStatus.ONLINE,
                        Worker.last_heartbeat < cutoff,
                    )
                )
                for w in rows.scalars().all():
                    w.status = WorkerStatus.OFFLINE
                await s.commit()
        except asyncio.CancelledError:
            raise
        except Exception:
            pass


async def _ensure_master_local_worker():
    """Idempotently create the master-local worker row using configured key."""
    node_id = settings.master_local_node_id
    api_key = settings.master_local_api_key
    if not node_id or not api_key:
        return
    async with async_session() as s:
        row = await s.execute(select(Worker).where(Worker.node_id == node_id))
        if row.scalar_one_or_none() is not None:
            return
        s.add(
            Worker(
                node_id=node_id,
                name=node_id,
                hostname=node_id,
                ip="127.0.0.1",
                port=8001,
                type=WorkerType.MASTER_LOCAL,
                api_key_hash=bcrypt.hashpw(api_key.encode(), bcrypt.gensalt()).decode(),
                status=WorkerStatus.OFFLINE,
                max_slots=4,
                labels=[],
            )
        )
        await s.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.started_at = datetime.now(timezone.utc)
    await ensure_seed_data()
    await _ensure_master_local_worker()
    sweep_task = asyncio.create_task(_offline_sweep())
    await scheduler_service.start()
    try:
        yield
    finally:
        sweep_task.cancel()
        try:
            await sweep_task
        except asyncio.CancelledError:
            pass
        await scheduler_service.shutdown()
        await redis_pool.aclose()


app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# HTTP metrics middleware (records latency histogram per route+method+status)
app.middleware("http")(http_metrics_middleware)

# Request ID middleware — inject/propagate X-Request-ID header for tracing
app.middleware("http")(request_id_middleware)


@app.get("/health")
async def health_check():
    return {"status": "ok"}


app.include_router(api_router)
app.include_router(ws_router)
app.include_router(metrics_router)  # GET /metrics (no auth, expose to Prometheus only)
