import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class ChannelType(StrEnum):
    DINGTALK = "dingtalk"
    FEISHU = "feishu"
    WECOM = "wecom"
    EMAIL = "email"


class EventType(StrEnum):
    TASK_FAILED = "task_failed"
    TASK_TIMEOUT = "task_timeout"
    TASK_KILLED = "task_killed"
    WORKER_OFFLINE = "worker_offline"


class EventStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class NotificationChannel(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "notification_channels"

    type: Mapped[ChannelType] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(128), unique=True)
    config_enc: Mapped[str] = mapped_column(Text)
    """Encrypted JSON: {webhook, secret, keyword, ...} or {smtp settings}."""
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    template: Mapped[str | None] = mapped_column(Text)
    """Optional Jinja2 message template. None = use built-in default.
    Available variables: {{event}}, {{task_name}}, {{task_id}}, {{run_id}},
    {{exit_code}}, {{error_msg}}, {{node_id}}.
    """


class NotificationRule(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "notification_rules"

    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("notification_channels.id", ondelete="CASCADE"),
    )
    event: Mapped[EventType] = mapped_column(String(32))
    filter: Mapped[dict | None] = mapped_column(JSONB, default=dict)


class NotificationEvent(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "notification_events"

    event: Mapped[EventType] = mapped_column(String(32))
    payload: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    status: Mapped[EventStatus] = mapped_column(
        String(16), default=EventStatus.PENDING
    )
    retry_no: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SmtpSettings(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "smtp_settings"

    host: Mapped[str] = mapped_column(String(128))
    port: Mapped[int] = mapped_column(Integer, default=587)
    username: Mapped[str | None] = mapped_column(String(128))
    password_enc: Mapped[str | None] = mapped_column(Text)
    from_addr: Mapped[str] = mapped_column(String(128))
    use_tls: Mapped[bool] = mapped_column(Boolean, default=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False)


class PersistentFile(Base):
    __tablename__ = "persistent_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    parent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("persistent_files.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    type: Mapped[str] = mapped_column(String(8), default="file")
    size: Mapped[int] = mapped_column(Integer, default=0)
    mtime: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    storage_path: Mapped[str | None] = mapped_column(String(1024))


class LogRetentionPolicy(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "log_retention_policies"

    name: Mapped[str] = mapped_column(String(64))
    days_to_keep: Mapped[int] = mapped_column(Integer, default=30)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
