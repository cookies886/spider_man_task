import secrets
import uuid
from datetime import datetime

from pydantic import Field

from app.models.worker import WorkerStatus, WorkerType
from app.schemas.base import BaseSchema, IDTimestampSchema


def generate_api_key() -> str:
    """Random URL-safe 32-byte API key."""
    return secrets.token_urlsafe(32)


class WorkerCreate(BaseSchema):
    """Admin creates a node entry; api_key is generated server-side."""

    name: str = Field(max_length=128)
    hostname: str = Field(max_length=128)
    ip: str = Field(max_length=45)
    port: int = Field(default=8001, ge=1, le=65535)
    type: WorkerType = WorkerType.REMOTE
    labels: list[str] | None = None
    max_slots: int = Field(default=4, ge=1, le=64)
    group_id: uuid.UUID | None = None


class WorkerUpdate(BaseSchema):
    """Admin edits a node entry. All fields optional."""

    name: str | None = Field(default=None, max_length=128)
    hostname: str | None = Field(default=None, max_length=128)
    ip: str | None = Field(default=None, max_length=45)
    port: int | None = Field(default=None, ge=1, le=65535)
    labels: list[str] | None = None
    max_slots: int | None = Field(default=None, ge=1, le=64)
    group_id: uuid.UUID | None = None


class WorkerCreated(IDTimestampSchema):
    """Returned ONCE on creation, includes plaintext api_key."""

    node_id: str
    name: str
    hostname: str
    ip: str
    port: int
    type: WorkerType
    api_key: str  # plaintext, shown once
    group_id: uuid.UUID | None = None


class WorkerRead(IDTimestampSchema):
    node_id: str
    name: str
    hostname: str
    ip: str
    port: int
    type: WorkerType
    os: str | None
    arch: str | None
    python_version: str | None
    status: WorkerStatus
    current_tasks: int
    max_slots: int
    labels: list | None
    cpu_usage: float
    mem_usage: float
    last_heartbeat: datetime | None
    group_id: uuid.UUID | None = None
