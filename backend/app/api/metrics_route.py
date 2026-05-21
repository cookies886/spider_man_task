"""Prometheus metrics endpoint."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Response
from sqlalchemy import func, select

from app.core.database import async_session
from app.core.metrics import (
    render_metrics,
    set_active_runs,
    set_workers_online,
)
from app.models.task import RunStatus, TaskRun
from app.models.worker import Worker, WorkerStatus

router = APIRouter()


@router.get("/metrics", include_in_schema=False)
async def metrics():
    """Prometheus exposition format. Refreshes gauges before rendering."""
    # Refresh point-in-time gauges (counts are cheap)
    try:
        async with async_session() as s:
            active = (
                await s.execute(
                    select(func.count(TaskRun.id)).where(
                        TaskRun.status.in_(
                            [
                                RunStatus.PENDING,
                                RunStatus.DISPATCHING,
                                RunStatus.RUNNING,
                            ]
                        )
                    )
                )
            ).scalar() or 0
            online = (
                await s.execute(
                    select(func.count(Worker.id)).where(
                        Worker.status == WorkerStatus.ONLINE
                    )
                )
            ).scalar() or 0
            # Touch-only timestamp side-effects deliberately omitted.
            _ = datetime.now(timezone.utc) - timedelta(seconds=0)
        set_active_runs(int(active))
        set_workers_online(int(online))
    except Exception:
        pass

    payload, content_type = render_metrics()
    return Response(content=payload, media_type=content_type)
