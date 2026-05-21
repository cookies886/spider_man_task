from pydantic import Field

from app.schemas.base import BaseSchema, IDTimestampSchema


class WorkerGroupCreate(BaseSchema):
    name: str = Field(max_length=64)
    description: str | None = Field(default=None, max_length=255)
    tags: list[str] | None = None


class WorkerGroupUpdate(BaseSchema):
    name: str | None = Field(default=None, max_length=64)
    description: str | None = Field(default=None, max_length=255)
    tags: list[str] | None = None


class WorkerGroupRead(IDTimestampSchema):
    name: str
    description: str | None
    tags: list | None
    worker_count: int = 0
