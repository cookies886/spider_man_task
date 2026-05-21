import uuid

from pydantic import Field

from app.schemas.base import BaseSchema, IDTimestampSchema


class EnvVarCreate(BaseSchema):
    project_id: uuid.UUID
    key: str = Field(max_length=128)
    value: str
    description: str | None = None
    is_secret: bool = True


class EnvVarUpdate(BaseSchema):
    key: str | None = Field(default=None, max_length=128)
    value: str | None = None
    description: str | None = None
    is_secret: bool | None = None


class EnvVarRead(IDTimestampSchema):
    project_id: uuid.UUID
    key: str
    value: str
    description: str | None
    is_secret: bool

    @classmethod
    def from_model(cls, env_var, *, mask_secret: bool = True) -> "EnvVarRead":
        """Create schema from model, masking secret values."""
        value = "***" if (mask_secret and env_var.is_secret) else env_var.value
        return cls(
            id=env_var.id,
            project_id=env_var.project_id,
            key=env_var.key,
            value=value,
            description=env_var.description,
            is_secret=env_var.is_secret,
            created_at=env_var.created_at,
            updated_at=env_var.updated_at,
        )
