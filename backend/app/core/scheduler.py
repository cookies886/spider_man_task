"""APScheduler-based task scheduler.

Loads all `is_active=True` tasks at startup, registers triggers, and on each
fire calls `runs.trigger_run(task_id)`. Use `register/unregister/refresh` from
API write paths to keep scheduler in sync with DB.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from app.core.database import async_session
from app.core.runs import trigger_run
from app.models.project import GitRepo
from app.models.task import ScheduleType, Task

logger = logging.getLogger(__name__)


class SchedulerService:
    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler(timezone="UTC")
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    async def start(self) -> None:
        async with async_session() as s:
            rows = await s.execute(
                select(Task).where(Task.is_active == True)  # noqa: E712
            )
            tasks = rows.scalars().all()
            git_rows = await s.execute(
                select(GitRepo).where(GitRepo.sync_interval_seconds.is_not(None))
            )
            git_repos = git_rows.scalars().all()
        for t in tasks:
            self._add_job(t)
        for r in git_repos:
            self.register_git_sync(r.project_id, r.sync_interval_seconds or 0)
        self._scheduler.start()
        self._running = True
        logger.info(
            "SchedulerService started: %d task jobs + %d git-sync jobs",
            sum(1 for j in self._scheduler.get_jobs() if j.id.startswith("task_")),
            sum(1 for j in self._scheduler.get_jobs() if j.id.startswith("gitsync_")),
        )

    async def shutdown(self) -> None:
        if self._running:
            self._scheduler.shutdown(wait=False)
            self._running = False

    @staticmethod
    def _job_id(task_id: uuid.UUID) -> str:
        return f"task_{task_id}"

    def _build_trigger(self, task: Task):
        cfg = task.schedule_config or {}
        if task.schedule_type == ScheduleType.CRON:
            expr = cfg.get("cron")
            if not expr:
                raise ValueError("cron task missing schedule_config.cron")
            return CronTrigger.from_crontab(expr, timezone="UTC")
        if task.schedule_type == ScheduleType.INTERVAL:
            seconds = int(cfg.get("interval_seconds") or 60)
            start_at = None
            if cfg.get("first_run_at"):
                try:
                    start_at = datetime.fromisoformat(cfg["first_run_at"])
                except ValueError:
                    pass
            return IntervalTrigger(seconds=seconds, start_date=start_at)
        if task.schedule_type == ScheduleType.ONCE:
            run_at_str = cfg.get("run_at")
            if not run_at_str:
                raise ValueError("once task missing schedule_config.run_at")
            return DateTrigger(run_date=datetime.fromisoformat(run_at_str))
        return None

    def _add_job(self, task: Task) -> None:
        if task.schedule_type == ScheduleType.IMMEDIATE:
            return
        try:
            trigger = self._build_trigger(task)
        except ValueError:
            logger.exception("bad trigger for task %s", task.id)
            return
        if trigger is None:
            return
        self._scheduler.add_job(
            _fire,
            trigger=trigger,
            id=self._job_id(task.id),
            kwargs={"task_id": task.id},
            replace_existing=True,
            misfire_grace_time=60,
            coalesce=True,
        )

    def register(self, task: Task) -> None:
        if not task.is_active:
            self.unregister(task.id)
            return
        self._add_job(task)

    def unregister(self, task_id: uuid.UUID) -> None:
        try:
            self._scheduler.remove_job(self._job_id(task_id))
        except JobLookupError:
            pass

    def refresh(self, task: Task) -> None:
        self.unregister(task.id)
        if task.is_active:
            self._add_job(task)

    # ---------- Git auto-pull jobs ----------

    @staticmethod
    def _git_job_id(project_id: uuid.UUID) -> str:
        return f"gitsync_{project_id}"

    def register_git_sync(self, project_id: uuid.UUID, interval_seconds: int) -> None:
        """Schedule a git pull every `interval_seconds`. Interval <= 0 unschedules."""
        self.unregister_git_sync(project_id)
        if interval_seconds <= 0:
            return
        self._scheduler.add_job(
            _fire_git_sync,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id=self._git_job_id(project_id),
            kwargs={"project_id": project_id},
            replace_existing=True,
            misfire_grace_time=300,
            coalesce=True,
        )

    def unregister_git_sync(self, project_id: uuid.UUID) -> None:
        try:
            self._scheduler.remove_job(self._git_job_id(project_id))
        except JobLookupError:
            pass

    def next_run(self, task_id: uuid.UUID) -> datetime | None:
        try:
            job = self._scheduler.get_job(self._job_id(task_id))
        except JobLookupError:
            return None
        return job.next_run_time if job else None


async def _fire(task_id: uuid.UUID):
    try:
        await trigger_run(task_id, triggered_by="scheduled")
    except Exception:
        logger.exception("trigger_run failed for %s", task_id)


async def _fire_git_sync(project_id: uuid.UUID):
    """Pull the latest commit + re-bundle zip. Errors are logged on the GitRepo row."""
    from app.core.git_sync import git_sync_service

    async with async_session() as s:
        try:
            await git_sync_service.sync(s, project_id)
            logger.info("git auto-sync ok for %s", project_id)
        except Exception:
            logger.exception("git auto-sync failed for %s", project_id)


scheduler_service = SchedulerService()
