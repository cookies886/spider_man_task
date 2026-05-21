import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class ScheduleType(StrEnum):
    IMMEDIATE = "immediate"
    INTERVAL = "interval"
    ONCE = "once"
    CRON = "cron"


class NodeStrategy(StrEnum):
    AUTO = "auto"
    MASTER = "master"
    SPECIFIC = "specific"
    GROUP = "group"
    PLATFORM = "platform"
    MIXED = "mixed"


class ConcurrentPolicy(StrEnum):
    SKIP = "skip"
    QUEUE = "queue"


class RunStatus(StrEnum):
    PENDING = "pending"
    DISPATCHING = "dispatching"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    KILLED = "killed"
    SKIPPED = "skipped"


class DependsOnStatus(StrEnum):
    SUCCESS = "success"
    ANY = "any"


class Task(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "tasks"

    name: Mapped[str] = mapped_column(String(128), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE")
    )
    env_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("environments.id", ondelete="SET NULL")
    )
    command: Mapped[str] = mapped_column(Text)
    schedule_type: Mapped[ScheduleType] = mapped_column(String(16))
    schedule_config: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    """One of:
    - {} for immediate
    - {"interval_seconds": int, "first_run_at": iso}
    - {"run_at": iso}
    - {"cron": "* * * * *"}"""
    node_strategy: Mapped[NodeStrategy] = mapped_column(
        String(16), default=NodeStrategy.AUTO
    )
    node_target: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    """For SPECIFIC: {"node_id": "..."}; for GROUP: {"group": "..."}; for PLATFORM: {"platform": "windows"}"""
    max_concurrent: Mapped[int] = mapped_column(Integer, default=1)
    concurrent_policy: Mapped[ConcurrentPolicy] = mapped_column(
        String(16), default=ConcurrentPolicy.SKIP
    )
    max_retries: Mapped[int] = mapped_column(Integer, default=0)
    timeout_sec: Mapped[int] = mapped_column(Integer, default=3600)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    tags: Mapped[list | None] = mapped_column(JSONB, default=list)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class TaskRun(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "task_runs"

    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    node_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workers.id", ondelete="SET NULL")
    )
    status: Mapped[RunStatus] = mapped_column(String(16), default=RunStatus.PENDING)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exit_code: Mapped[int | None] = mapped_column(Integer)
    retry_no: Mapped[int] = mapped_column(Integer, default=0)
    log_file_path: Mapped[str | None] = mapped_column(String(512))
    error_msg: Mapped[str | None] = mapped_column(Text)
    triggered_by: Mapped[str | None] = mapped_column(String(32))
    """One of: scheduled / manual / dependency"""


class TaskDependency(Base):
    __tablename__ = "task_dependencies"
    __table_args__ = (
        UniqueConstraint("task_id", "upstream_task_id", name="uq_task_dep"),
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        primary_key=True,
    )
    upstream_task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        primary_key=True,
    )
    on_status: Mapped[DependsOnStatus] = mapped_column(
        String(16), default=DependsOnStatus.SUCCESS
    )


# Backwards-compat aliases (will be cleaned in slice 7)
TaskStatus = RunStatus
TaskTriggerType = ScheduleType
