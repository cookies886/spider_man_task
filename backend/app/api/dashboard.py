"""Dashboard aggregation API."""
from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import case, desc, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.deps import get_current_user
from app.core.redis import get_redis
from app.models.environment import Environment
from app.models.project import Project
from app.models.task import RunStatus, Task, TaskRun
from app.models.worker import Worker, WorkerGroup, WorkerMetric, WorkerStatus

router = APIRouter(
    prefix="/dashboard", tags=["dashboard"], dependencies=[Depends(get_current_user)]
)

CACHE_TTL = 60


def _range_to_seconds(rng: str) -> int:
    return {"1h": 3600, "6h": 21600, "24h": 86400, "7d": 604800, "30d": 2592000}.get(
        rng, 86400
    )


async def _cached(key: str, builder):
    redis = await get_redis()
    try:
        cached = await redis.get(key)
        if cached:
            return json.loads(cached)
        data = await builder()
        await redis.set(key, json.dumps(data, default=str), ex=CACHE_TTL)
        return data
    finally:
        await redis.aclose()


# ---------------- overview ----------------


@router.get("/overview")
async def overview(
    request: Request, session: AsyncSession = Depends(get_session)
):
    async def build():
        total_projects = (
            await session.execute(select(func.count(Project.id)))
        ).scalar() or 0
        total_tasks = (
            await session.execute(select(func.count(Task.id)))
        ).scalar() or 0
        active_tasks = (
            await session.execute(
                select(func.count(Task.id)).where(Task.is_active == True)  # noqa: E712
            )
        ).scalar() or 0
        paused_tasks = total_tasks - active_tasks
        total_envs = (
            await session.execute(select(func.count(Environment.id)))
        ).scalar() or 0
        total_workers = (
            await session.execute(select(func.count(Worker.id)))
        ).scalar() or 0
        online_workers = (
            await session.execute(
                select(func.count(Worker.id)).where(
                    Worker.status == WorkerStatus.ONLINE
                )
            )
        ).scalar() or 0
        running_runs = (
            await session.execute(
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
        today = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        today_total = (
            await session.execute(
                select(func.count(TaskRun.id)).where(TaskRun.created_at >= today)
            )
        ).scalar() or 0
        today_success = (
            await session.execute(
                select(func.count(TaskRun.id)).where(
                    TaskRun.created_at >= today,
                    TaskRun.status == RunStatus.SUCCESS,
                )
            )
        ).scalar() or 0
        success_rate = (today_success / today_total) if today_total else 0.0
        cluster_health = (
            "healthy"
            if total_workers > 0 and online_workers == total_workers
            else "degraded"
            if online_workers > 0
            else "down"
        )

        # services availability probes
        services = {"master": "healthy", "postgres": "down", "redis": "down"}
        try:
            await session.execute(select(1))
            services["postgres"] = "healthy"
        except SQLAlchemyError:
            pass
        try:
            r = await get_redis()
            try:
                await r.ping()
                services["redis"] = "healthy"
            finally:
                await r.aclose()
        except Exception:
            pass

        # recent failures: last 5 failed/timeout/killed runs
        rf_rows = (
            await session.execute(
                select(TaskRun, Task.name)
                .join(Task, Task.id == TaskRun.task_id)
                .where(
                    TaskRun.status.in_(
                        [
                            RunStatus.FAILED,
                            RunStatus.TIMEOUT,
                            RunStatus.KILLED,
                        ]
                    )
                )
                .order_by(desc(TaskRun.finished_at), desc(TaskRun.created_at))
                .limit(5)
            )
        ).all()
        recent_failures = [
            {
                "run_id": str(r.TaskRun.id),
                "task_id": str(r.TaskRun.task_id),
                "task_name": r.name,
                "status": r.TaskRun.status,
                "finished_at": r.TaskRun.finished_at.isoformat()
                if r.TaskRun.finished_at
                else None,
                "error_msg": r.TaskRun.error_msg,
            }
            for r in rf_rows
        ]

        # uptime
        started_at = getattr(request.app.state, "started_at", None)
        uptime_seconds = (
            int((datetime.now(timezone.utc) - started_at).total_seconds())
            if started_at
            else 0
        )

        return {
            "total_projects": total_projects,
            "total_tasks": total_tasks,
            "active_tasks": active_tasks,
            "paused_tasks": paused_tasks,
            "total_envs": total_envs,
            "total_workers": total_workers,
            "online_workers": online_workers,
            "running_runs": running_runs,
            "today_total": today_total,
            "today_success": today_success,
            "success_rate": round(success_rate, 4),
            "cluster_health": cluster_health,
            "uptime_seconds": uptime_seconds,
            "services": services,
            "recent_failures": recent_failures,
        }

    return await _cached("dash:overview", build)


# ---------------- perf ----------------


def _stats(values: list[float]) -> dict:
    if not values:
        return {"peak": 0, "avg": 0, "anomaly_count": 0}
    peak = max(values)
    avg = sum(values) / len(values)
    if len(values) >= 2:
        var = sum((v - avg) ** 2 for v in values) / len(values)
        sd = math.sqrt(var)
        threshold = avg + 2 * sd
        anomaly = sum(1 for v in values if v > threshold)
    else:
        anomaly = 0
    return {
        "peak": round(peak, 2),
        "avg": round(avg, 2),
        "anomaly_count": int(anomaly),
    }


@router.get("/perf")
async def perf(
    range_: str = Query(default="1h", alias="range"),
    session: AsyncSession = Depends(get_session),
):
    async def build():
        cutoff = datetime.now(timezone.utc) - timedelta(
            seconds=_range_to_seconds(range_)
        )
        rows = (
            await session.execute(
                select(
                    WorkerMetric.ts,
                    func.avg(WorkerMetric.cpu_pct).label("cpu"),
                    func.avg(WorkerMetric.mem_pct).label("mem"),
                    func.avg(WorkerMetric.disk_pct).label("disk"),
                    func.sum(WorkerMetric.net_in_bps).label("net_in"),
                    func.sum(WorkerMetric.net_out_bps).label("net_out"),
                )
                .where(WorkerMetric.ts >= cutoff)
                .group_by(WorkerMetric.ts)
                .order_by(WorkerMetric.ts)
            )
        ).all()
        series = [
            {
                "ts": r.ts.isoformat(),
                "cpu": round(float(r.cpu or 0), 2),
                "mem": round(float(r.mem or 0), 2),
                "disk": round(float(r.disk or 0), 2),
                "net_in": int(r.net_in or 0),
                "net_out": int(r.net_out or 0),
            }
            for r in rows
        ]

        stats = {
            "cpu": _stats([s["cpu"] for s in series]),
            "mem": _stats([s["mem"] for s in series]),
            "disk": _stats([s["disk"] for s in series]),
            "net_in": _stats([s["net_in"] for s in series]),
            "net_out": _stats([s["net_out"] for s in series]),
        }

        # per-node aggregate
        per_node_rows = (
            await session.execute(
                select(
                    Worker.node_id,
                    Worker.name,
                    func.avg(WorkerMetric.cpu_pct).label("cpu"),
                    func.avg(WorkerMetric.mem_pct).label("mem"),
                    func.avg(WorkerMetric.disk_pct).label("disk"),
                )
                .join(WorkerMetric, WorkerMetric.worker_id == Worker.id)
                .where(WorkerMetric.ts >= cutoff)
                .group_by(Worker.node_id, Worker.name)
                .order_by(desc("cpu"))
            )
        ).all()
        per_node = [
            {
                "node_id": r.node_id,
                "name": r.name,
                "cpu": round(float(r.cpu or 0), 2),
                "mem": round(float(r.mem or 0), 2),
                "disk": round(float(r.disk or 0), 2),
            }
            for r in per_node_rows
        ]

        latest = (
            await session.execute(
                select(
                    Worker.node_id, Worker.cpu_usage, Worker.mem_usage, Worker.status
                )
            )
        ).all()
        return {
            "series": series,
            "stats": stats,
            "per_node": per_node,
            "workers": [
                {
                    "node_id": w.node_id,
                    "cpu": w.cpu_usage,
                    "mem": w.mem_usage,
                    "status": w.status,
                }
                for w in latest
            ],
        }

    return await _cached(f"dash:perf:{range_}", build)


# ---------------- tasks ----------------


_GRAN_TRUNC = {"hour": "hour", "day": "day", "month": "month"}


@router.get("/tasks")
async def tasks_dashboard(
    range_: str = Query(default="24h", alias="range"),
    granularity: str = Query(default="hour"),
    session: AsyncSession = Depends(get_session),
):
    gran = _GRAN_TRUNC.get(granularity, "hour")

    async def build():
        secs = _range_to_seconds(range_)
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=secs)

        status_rows = (
            await session.execute(
                select(TaskRun.status, func.count(TaskRun.id))
                .where(TaskRun.created_at >= cutoff)
                .group_by(TaskRun.status)
            )
        ).all()
        status_counts = {r[0]: r[1] for r in status_rows}

        total = sum(status_counts.values())
        success = status_counts.get(RunStatus.SUCCESS, 0)
        failed = status_counts.get(RunStatus.FAILED, 0)
        timeout = status_counts.get(RunStatus.TIMEOUT, 0)
        killed = status_counts.get(RunStatus.KILLED, 0)
        skipped = status_counts.get(RunStatus.SKIPPED, 0)
        pending = status_counts.get(RunStatus.PENDING, 0)
        dispatching = status_counts.get(RunStatus.DISPATCHING, 0)
        running = status_counts.get(RunStatus.RUNNING, 0)
        paused_tasks = (
            await session.execute(
                select(func.count(Task.id)).where(Task.is_active == False)  # noqa: E712
            )
        ).scalar() or 0

        avg_duration = (
            await session.execute(
                select(
                    func.avg(
                        func.extract(
                            "epoch", TaskRun.finished_at - TaskRun.started_at
                        )
                    )
                ).where(
                    TaskRun.created_at >= cutoff,
                    TaskRun.started_at.is_not(None),
                    TaskRun.finished_at.is_not(None),
                )
            )
        ).scalar() or 0

        # trend by granularity
        trend_rows = (
            await session.execute(
                select(
                    func.date_trunc(gran, TaskRun.created_at).label("bucket"),
                    func.count(TaskRun.id),
                    func.sum(
                        case((TaskRun.status == RunStatus.SUCCESS, 1), else_=0)
                    ),
                )
                .where(TaskRun.created_at >= cutoff)
                .group_by("bucket")
                .order_by("bucket")
            )
        ).all()
        trend = [
            {
                "bucket": r.bucket.isoformat() if r.bucket else None,
                "total": r[1],
                "success": int(r[2] or 0),
            }
            for r in trend_rows
        ]

        # 24h hour distribution (last 7 days)
        last_7d = datetime.now(timezone.utc) - timedelta(days=7)
        dist = (
            await session.execute(
                select(
                    func.extract("hour", TaskRun.created_at).label("h"),
                    func.count(TaskRun.id),
                )
                .where(TaskRun.created_at >= last_7d)
                .group_by("h")
                .order_by("h")
            )
        ).all()
        dist_map = {int(r.h): r[1] for r in dist}
        hour_distribution = [
            {"hour": h, "count": dist_map.get(h, 0)} for h in range(24)
        ]

        # 60d calendar
        last_60d = datetime.now(timezone.utc) - timedelta(days=60)
        cal = (
            await session.execute(
                select(
                    func.date(TaskRun.created_at).label("d"),
                    func.count(TaskRun.id),
                )
                .where(TaskRun.created_at >= last_60d)
                .group_by("d")
                .order_by("d")
            )
        ).all()

        # duration histogram (over `range` window)
        dur_rows = (
            await session.execute(
                select(
                    func.extract(
                        "epoch", TaskRun.finished_at - TaskRun.started_at
                    ).label("sec")
                ).where(
                    TaskRun.created_at >= cutoff,
                    TaskRun.started_at.is_not(None),
                    TaskRun.finished_at.is_not(None),
                )
            )
        ).all()
        buckets = [
            (0, 5, "<5s"),
            (5, 30, "5-30s"),
            (30, 120, "30s-2m"),
            (120, 600, "2-10m"),
            (600, 3600, "10m-1h"),
            (3600, float("inf"), ">1h"),
        ]
        hist_counts = [0] * len(buckets)
        for r in dur_rows:
            sec = float(r.sec or 0)
            for i, (lo, hi, _) in enumerate(buckets):
                if lo <= sec < hi:
                    hist_counts[i] += 1
                    break
        duration_histogram = [
            {"bucket": label, "count": cnt}
            for (_, _, label), cnt in zip(buckets, hist_counts)
        ]

        # node distribution
        node_rows = (
            await session.execute(
                select(
                    Worker.node_id,
                    Worker.name,
                    func.count(TaskRun.id),
                    func.sum(
                        case((TaskRun.status == RunStatus.SUCCESS, 1), else_=0)
                    ),
                )
                .join(Worker, Worker.id == TaskRun.node_id)
                .where(TaskRun.created_at >= cutoff)
                .group_by(Worker.node_id, Worker.name)
                .order_by(desc(func.count(TaskRun.id)))
            )
        ).all()
        node_distribution = [
            {
                "node_id": r.node_id,
                "name": r.name,
                "total": r[2],
                "success": int(r[3] or 0),
                "success_rate": round((r[3] or 0) / r[2], 4) if r[2] else 0.0,
            }
            for r in node_rows
        ]

        # project ranking (top 10)
        proj_rows = (
            await session.execute(
                select(
                    Project.id,
                    Project.name,
                    func.count(TaskRun.id),
                    func.sum(
                        case((TaskRun.status == RunStatus.SUCCESS, 1), else_=0)
                    ),
                )
                .join(Task, Task.id == TaskRun.task_id)
                .join(Project, Project.id == Task.project_id)
                .where(TaskRun.created_at >= cutoff)
                .group_by(Project.id, Project.name)
                .order_by(desc(func.count(TaskRun.id)))
                .limit(10)
            )
        ).all()
        project_ranking = [
            {
                "project_id": str(r.id),
                "name": r.name,
                "total": r[2],
                "success": int(r[3] or 0),
                "success_rate": round((r[3] or 0) / r[2], 4) if r[2] else 0.0,
            }
            for r in proj_rows
        ]

        return {
            "summary": {
                "total": total,
                "success": success,
                "failed": failed,
                "timeout": timeout,
                "killed": killed,
                "skipped": skipped,
                "running": running,
                "pending": pending,
                "dispatching": dispatching,
                "paused_tasks": int(paused_tasks),
                "success_rate": round(success / total, 4) if total else 0.0,
                "avg_duration_sec": round(float(avg_duration), 2),
            },
            "granularity": gran,
            "trend": trend,
            "hour_distribution": hour_distribution,
            "calendar": [{"date": str(r.d), "count": r[1]} for r in cal],
            "duration_histogram": duration_histogram,
            "node_distribution": node_distribution,
            "project_ranking": project_ranking,
        }

    return await _cached(f"dash:tasks:{range_}:{gran}", build)


# ---------------- workers ----------------


@router.get("/workers")
async def workers_dashboard(
    session: AsyncSession = Depends(get_session),
):
    async def build():
        rows = (
            await session.execute(
                select(Worker, WorkerGroup.name)
                .join(WorkerGroup, WorkerGroup.id == Worker.group_id, isouter=True)
                .order_by(
                    case((Worker.status == WorkerStatus.ONLINE, 0), else_=1),
                    Worker.name,
                )
            )
        ).all()
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        items = []
        for w, group_name in rows:
            # 1h time series
            metric_rows = (
                await session.execute(
                    select(WorkerMetric)
                    .where(
                        WorkerMetric.worker_id == w.id,
                        WorkerMetric.ts >= cutoff,
                    )
                    .order_by(WorkerMetric.ts)
                )
            ).scalars().all()
            history = [
                {
                    "ts": m.ts.isoformat(),
                    "cpu": round(m.cpu_pct, 2),
                    "mem": round(m.mem_pct, 2),
                    "disk": round(m.disk_pct, 2),
                }
                for m in metric_rows
            ]

            # task summary (24h)
            day_cutoff = datetime.now(timezone.utc) - timedelta(days=1)
            ts_rows = (
                await session.execute(
                    select(
                        func.count(TaskRun.id),
                        func.sum(
                            case(
                                (TaskRun.status == RunStatus.SUCCESS, 1),
                                else_=0,
                            )
                        ),
                        func.sum(
                            case(
                                (TaskRun.status == RunStatus.FAILED, 1),
                                else_=0,
                            )
                        ),
                    ).where(
                        TaskRun.node_id == w.id,
                        TaskRun.created_at >= day_cutoff,
                    )
                )
            ).first()
            t_total = int(ts_rows[0] or 0) if ts_rows else 0
            t_succ = int(ts_rows[1] or 0) if ts_rows else 0
            t_fail = int(ts_rows[2] or 0) if ts_rows else 0
            task_summary = {
                "total": t_total,
                "success": t_succ,
                "failed": t_fail,
                "success_rate": round(t_succ / t_total, 4) if t_total else 0.0,
            }

            # uptime: time since first heartbeat ever in worker_metrics, or
            # else since worker was registered (created_at)
            first_metric_ts = (
                await session.execute(
                    select(func.min(WorkerMetric.ts)).where(
                        WorkerMetric.worker_id == w.id
                    )
                )
            ).scalar()
            anchor = first_metric_ts or w.created_at
            if w.last_heartbeat and anchor:
                uptime_seconds = int((w.last_heartbeat - anchor).total_seconds())
            else:
                uptime_seconds = 0

            # connection quality based on heartbeat freshness
            if w.last_heartbeat is None:
                conn_quality = "never"
            else:
                now = datetime.now(timezone.utc)
                gap = (now - w.last_heartbeat).total_seconds()
                if gap < 15:
                    conn_quality = "excellent"
                elif gap < 60:
                    conn_quality = "good"
                elif gap < 180:
                    conn_quality = "poor"
                else:
                    conn_quality = "lost"

            items.append(
                {
                    "id": str(w.id),
                    "node_id": w.node_id,
                    "name": w.name,
                    "type": w.type,
                    "status": w.status,
                    "hostname": w.hostname,
                    "ip": w.ip,
                    "port": w.port,
                    "os": w.os,
                    "arch": w.arch,
                    "python_version": w.python_version,
                    "labels": w.labels or [],
                    "group_id": str(w.group_id) if w.group_id else None,
                    "group_name": group_name,
                    "max_slots": w.max_slots,
                    "current_tasks": w.current_tasks,
                    "cpu_usage": round(w.cpu_usage, 2),
                    "mem_usage": round(w.mem_usage, 2),
                    "last_heartbeat": w.last_heartbeat.isoformat()
                    if w.last_heartbeat
                    else None,
                    "uptime_seconds": uptime_seconds,
                    "connection_quality": conn_quality,
                    "history": history,
                    "task_summary": task_summary,
                }
            )
        return {"items": items}

    return await _cached("dash:workers", build)


# ---------------- charts (指标图表) ----------------


@router.get("/charts")
async def charts(
    range_: str = Query(default="24h", alias="range"),
    granularity: str = Query(default="hour"),
    session: AsyncSession = Depends(get_session),
):
    gran = _GRAN_TRUNC.get(granularity, "hour")

    async def build():
        cutoff = datetime.now(timezone.utc) - timedelta(
            seconds=_range_to_seconds(range_)
        )

        # execution volume + success rate by bucket
        vol_rows = (
            await session.execute(
                select(
                    func.date_trunc(gran, TaskRun.created_at).label("bucket"),
                    func.count(TaskRun.id),
                    func.sum(
                        case((TaskRun.status == RunStatus.SUCCESS, 1), else_=0)
                    ),
                )
                .where(TaskRun.created_at >= cutoff)
                .group_by("bucket")
                .order_by("bucket")
            )
        ).all()
        execution_volume = [
            {
                "bucket": r.bucket.isoformat() if r.bucket else None,
                "total": r[1],
                "success": int(r[2] or 0),
                "success_rate": round((r[2] or 0) / r[1], 4) if r[1] else 0.0,
            }
            for r in vol_rows
        ]

        # task type distribution by schedule_type
        type_rows = (
            await session.execute(
                select(Task.schedule_type, func.count(TaskRun.id))
                .join(TaskRun, TaskRun.task_id == Task.id)
                .where(TaskRun.created_at >= cutoff)
                .group_by(Task.schedule_type)
            )
        ).all()
        task_type_distribution = [
            {"name": str(r[0]), "value": r[1]} for r in type_rows
        ]

        # project load distribution
        proj_rows = (
            await session.execute(
                select(Project.name, func.count(TaskRun.id))
                .join(Task, Task.project_id == Project.id)
                .join(TaskRun, TaskRun.task_id == Task.id)
                .where(TaskRun.created_at >= cutoff)
                .group_by(Project.name)
                .order_by(desc(func.count(TaskRun.id)))
                .limit(10)
            )
        ).all()
        project_load = [{"name": r[0], "value": r[1]} for r in proj_rows]

        # node load (use TaskRun.node_id → Worker.node_id mapping)
        node_rows = (
            await session.execute(
                select(Worker.node_id, func.count(TaskRun.id))
                .join(TaskRun, TaskRun.node_id == Worker.id)
                .where(TaskRun.created_at >= cutoff)
                .group_by(Worker.node_id)
                .order_by(desc(func.count(TaskRun.id)))
            )
        ).all()
        node_load = [{"name": r[0], "value": r[1]} for r in node_rows]

        return {
            "granularity": gran,
            "execution_volume": execution_volume,
            "task_type_distribution": task_type_distribution,
            "project_load": project_load,
            "node_load": node_load,
        }

    return await _cached(f"dash:charts:{range_}:{gran}", build)


# ---------------- gantt (kept) ----------------


@router.get("/gantt")
async def gantt(
    date_: str | None = Query(default=None, alias="date"),
    session: AsyncSession = Depends(get_session),
):
    if date_:
        try:
            d = date.fromisoformat(date_)
        except ValueError:
            d = datetime.now(timezone.utc).date()
    else:
        d = datetime.now(timezone.utc).date()

    async def build():
        start = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
        end = start + timedelta(days=1)
        rows = (
            await session.execute(
                select(TaskRun, Task.name)
                .join(Task, TaskRun.task_id == Task.id)
                .where(TaskRun.started_at >= start, TaskRun.started_at < end)
                .order_by(TaskRun.started_at)
            )
        ).all()
        return {
            "date": str(d),
            "items": [
                {
                    "run_id": str(r.TaskRun.id),
                    "task_id": str(r.TaskRun.task_id),
                    "task_name": r.name,
                    "started_at": r.TaskRun.started_at.isoformat()
                    if r.TaskRun.started_at
                    else None,
                    "finished_at": r.TaskRun.finished_at.isoformat()
                    if r.TaskRun.finished_at
                    else None,
                    "status": r.TaskRun.status,
                    "node_id": str(r.TaskRun.node_id) if r.TaskRun.node_id else None,
                }
                for r in rows
            ],
        }

    return await _cached(f"dash:gantt:{d}", build)
