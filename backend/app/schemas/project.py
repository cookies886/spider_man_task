import uuid
from datetime import datetime

from pydantic import Field

from app.models.project import DistributionStatus, SourceType
from app.schemas.base import BaseSchema, IDTimestampSchema


class GitRepoConfig(BaseSchema):
    url: str = Field(max_length=512)
    branch: str = Field(default="main", max_length=128)
    username: str | None = None
    password: str | None = None
    sync_interval_seconds: int | None = Field(default=None, ge=60)


class ProjectCreate(BaseSchema):
    name: str = Field(max_length=128)
    description: str | None = None
    source_type: SourceType
    work_path: str = Field(default="/", max_length=256)
    default_node_id: uuid.UUID | None = None
    default_env_id: uuid.UUID | None = None
    tags: list[str] | None = None
    git: GitRepoConfig | None = None


class ProjectUpdate(BaseSchema):
    description: str | None = None
    work_path: str | None = Field(default=None, max_length=256)
    default_node_id: uuid.UUID | None = None
    default_env_id: uuid.UUID | None = None
    tags: list[str] | None = None


class ProjectRead(IDTimestampSchema):
    name: str
    description: str | None
    source_type: SourceType
    work_path: str
    owner_id: uuid.UUID | None
    default_node_id: uuid.UUID | None
    default_env_id: uuid.UUID | None
    tags: list | None
    current_hash: str | None


class GitRepoRead(BaseSchema):
    url: str
    branch: str
    username: str | None
    sync_interval_seconds: int | None
    last_sync_at: datetime | None
    last_commit: str | None
    last_error: str | None


class DistributionRead(BaseSchema):
    node_id: uuid.UUID
    status: DistributionStatus
    last_synced_at: datetime | None
    current_hash: str | None
    last_error: str | None


class ProjectDetail(ProjectRead):
    git: GitRepoRead | None = None
    distributions: list[DistributionRead] = []


class ProjectFileEntry(BaseSchema):
    name: str
    path: str
    is_dir: bool
    size: int
    mtime: datetime


class FileWriteBody(BaseSchema):
    content: str


class GitSyncResult(BaseSchema):
    last_commit: str
    last_sync_at: datetime
    files_changed: int
