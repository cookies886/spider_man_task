import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class ConditionType(StrEnum):
    TASK_FAIL = "task_fail"
    TASK_TIMEOUT = "task_timeout"
    WORKER_OFFLINE = "worker_offline"
    CONSECUTIVE_FAIL = "consecutive_fail"


class AlertSendStatus(StrEnum):
    SENT = "sent"
    FAILED = "failed"


class AlertRule(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "alert_rules"

    name: Mapped[str] = mapped_column(String(128))
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE")
    )
    condition_type: Mapped[ConditionType] = mapped_column(String(32))
    threshold: Mapped[int] = mapped_column(Integer, default=1)
    channels: Mapped[dict] = mapped_column(JSONB)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class AlertHistory(UUIDMixin, Base):
    __tablename__ = "alert_history"

    rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("alert_rules.id", ondelete="CASCADE")
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    worker_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    message: Mapped[str] = mapped_column(Text)
    channel: Mapped[str] = mapped_column(String(32))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[AlertSendStatus] = mapped_column(String(16))
