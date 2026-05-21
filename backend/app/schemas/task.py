import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from app.models.task import (
    ConcurrentPolicy,
    DependsOnStatus,
    NodeStrategy,
    RunStatus,
    ScheduleType,
)
from app.schemas.base import BaseSchema, IDTimestampSchema


class TaskCreate(BaseSchema):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    project_id: uuid.UUID
    env_id: uuid.UUID | None = None
    command: str = Field(min_length=1)
    schedule_type: ScheduleType
    schedule_config: dict[str, Any] | None = None
    node_strategy: NodeStrategy = NodeStrategy.AUTO
    node_target: dict[str, Any] | None = None
    max_concurrent: int = Field(default=1, ge=1, le=64)
    concurrent_policy: ConcurrentPolicy = ConcurrentPolicy.SKIP
    max_retries: int = Field(default=0, ge=0, le=10)
    timeout_sec: int = Field(default=3600, ge=1, le=86400)
    is_active: bool = True
    tags: list[str] | None = None
    depends_on: list[uuid.UUID] | None = None


class TaskUpdate(BaseSchema):
    description: str | None = None
    env_id: uuid.UUID | None = None
    command: str | None = None
    schedule_type: ScheduleType | None = None
    schedule_config: dict[str, Any] | None = None
    node_strategy: NodeStrategy | None = None
    node_target: dict[str, Any] | None = None
    max_concurrent: int | None = Field(default=None, ge=1, le=64)
    concurrent_policy: ConcurrentPolicy | None = None
    max_retries: int | None = Field(default=None, ge=0, le=10)
    timeout_sec: int | None = Field(default=None, ge=1, le=86400)
    is_active: bool | None = None
    tags: list[str] | None = None


class TaskRead(IDTimestampSchema):
    name: str
    description: str | None
    project_id: uuid.UUID
    env_id: uuid.UUID | None
    command: str
    schedule_type: ScheduleType
    schedule_config: dict | None
    node_strategy: NodeStrategy
    node_target: dict | None
    max_concurrent: int
    concurrent_policy: ConcurrentPolicy
    max_retries: int
    timeout_sec: int
    is_active: bool
    tags: list | None
    owner_id: uuid.UUID | None


class TaskDetail(TaskRead):
    depends_on: list[uuid.UUID] = []
    next_run_at: datetime | None = None


class TaskRunRead(IDTimestampSchema):
    task_id: uuid.UUID
    node_id: uuid.UUID | None
    status: RunStatus
    started_at: datetime | None
    finished_at: datetime | None
    exit_code: int | None
    retry_no: int
    error_msg: str | None
    triggered_by: str | None


class DependencyAdd(BaseSchema):
    upstream_task_id: uuid.UUID
    on_status: DependsOnStatus = DependsOnStatus.SUCCESS
