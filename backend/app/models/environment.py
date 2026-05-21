import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class EnvStatus(StrEnum):
    CREATING = "creating"
    READY = "ready"
    UPDATING = "updating"
    FAILED = "failed"


class PyVerStatus(StrEnum):
    DOWNLOADING = "downloading"
    BUILDING = "building"
    READY = "ready"
    FAILED = "failed"


class PythonVersion(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "python_versions"

    version: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    status: Mapped[PyVerStatus] = mapped_column(
        String(16), default=PyVerStatus.DOWNLOADING
    )
    tarball_url: Mapped[str | None] = mapped_column(String(512))
    install_path: Mapped[str | None] = mapped_column(String(512))
    build_log_path: Mapped[str | None] = mapped_column(String(512))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    error_msg: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class MirrorSource(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "mirror_sources"

    name: Mapped[str] = mapped_column(String(64), unique=True)
    url: Mapped[str] = mapped_column(String(512))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)


class Environment(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "environments"

    name: Mapped[str] = mapped_column(String(128), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    node_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workers.id", ondelete="SET NULL")
    )
    python_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("python_versions.id", ondelete="SET NULL")
    )
    mirror_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mirror_sources.id", ondelete="SET NULL")
    )
    requirements: Mapped[str | None] = mapped_column(Text)
    venv_path: Mapped[str | None] = mapped_column(String(512))
    install_log_path: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[EnvStatus] = mapped_column(
        String(16), default=EnvStatus.CREATING
    )
    tags: Mapped[list | None] = mapped_column(JSONB, default=list)
    error_msg: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class EnvironmentCollaborator(Base):
    __tablename__ = "environment_collaborators"

    env_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("environments.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
