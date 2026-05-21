import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class WorkerStatus(StrEnum):
    ONLINE = "online"
    OFFLINE = "offline"
    BUSY = "busy"
    DISABLED = "disabled"


class WorkerType(StrEnum):
    MASTER_LOCAL = "master_local"
    REMOTE = "remote"


class WorkerGroup(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "worker_groups"

    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(String(255))
    tags: Mapped[list | None] = mapped_column(JSONB, default=list)


class Worker(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "workers"

    node_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    hostname: Mapped[str] = mapped_column(String(128))
    ip: Mapped[str] = mapped_column(String(45))
    port: Mapped[int] = mapped_column(Integer, default=8001)
    type: Mapped[WorkerType] = mapped_column(String(16), default=WorkerType.REMOTE)
    os: Mapped[str | None] = mapped_column(String(32))
    arch: Mapped[str | None] = mapped_column(String(32))
    python_version: Mapped[str | None] = mapped_column(String(32))
    api_key_hash: Mapped[str] = mapped_column(String(128))
    labels: Mapped[dict | None] = mapped_column(JSONB, default=list)
    max_slots: Mapped[int] = mapped_column(Integer, default=4)
    status: Mapped[WorkerStatus] = mapped_column(String(16), default=WorkerStatus.OFFLINE)
    cpu_usage: Mapped[float] = mapped_column(Float, default=0.0)
    mem_usage: Mapped[float] = mapped_column(Float, default=0.0)
    current_tasks: Mapped[int] = mapped_column(Integer, default=0)
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    group_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("worker_groups.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )


class WorkerMetric(Base):
    __tablename__ = "worker_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    worker_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workers.id", ondelete="CASCADE"),
        index=True,
    )
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    cpu_pct: Mapped[float] = mapped_column(Float, default=0.0)
    mem_pct: Mapped[float] = mapped_column(Float, default=0.0)
    disk_pct: Mapped[float] = mapped_column(Float, default=0.0)
    net_in_bps: Mapped[int] = mapped_column(BigInteger, default=0)
    net_out_bps: Mapped[int] = mapped_column(BigInteger, default=0)
    running_tasks: Mapped[int] = mapped_column(Integer, default=0)
