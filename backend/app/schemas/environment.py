import uuid

from pydantic import Field

from app.models.environment import EnvStatus, PyVerStatus
from app.schemas.base import BaseSchema, IDTimestampSchema


class PythonVersionCreate(BaseSchema):
    version: str = Field(min_length=2, max_length=32)
    tarball_url: str = Field(max_length=512)


class PythonVersionRead(IDTimestampSchema):
    version: str
    status: PyVerStatus
    tarball_url: str | None
    install_path: str | None
    is_default: bool
    error_msg: str | None


class MirrorCreate(BaseSchema):
    name: str = Field(max_length=64)
    url: str = Field(max_length=512)
    is_default: bool = False


class MirrorRead(IDTimestampSchema):
    name: str
    url: str
    is_default: bool
    is_builtin: bool


class EnvironmentCreate(BaseSchema):
    name: str = Field(max_length=128)
    description: str | None = None
    node_id: uuid.UUID | None = None
    python_version_id: uuid.UUID | None = None
    mirror_id: uuid.UUID | None = None
    requirements: str | None = None
    tags: list[str] | None = None


class EnvironmentUpdate(BaseSchema):
    description: str | None = None
    requirements: str | None = None
    mirror_id: uuid.UUID | None = None
    tags: list[str] | None = None


class EnvironmentRead(IDTimestampSchema):
    name: str
    description: str | None
    node_id: uuid.UUID | None
    python_version_id: uuid.UUID | None
    mirror_id: uuid.UUID | None
    requirements: str | None
    venv_path: str | None
    status: EnvStatus
    tags: list | None
    error_msg: str | None
    owner_id: uuid.UUID | None
