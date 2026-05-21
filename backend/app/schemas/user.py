import uuid
from datetime import datetime

from pydantic import Field

from app.schemas.base import BaseSchema, IDTimestampSchema


class MeResponse(BaseSchema):
    id: uuid.UUID
    username: str
    full_name: str | None
    email: str | None
    is_superuser: bool
    must_change_password: bool
    permissions: list[str]
    page_acls: list[str]
    last_login_at: datetime | None


class PasswordChange(BaseSchema):
    old_password: str
    new_password: str = Field(min_length=8)


class UserCreate(BaseSchema):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=8)
    email: str | None = None
    full_name: str | None = None
    is_active: bool = True
    role_codes: list[str] = []
    page_acls: list[str] = []


class UserUpdate(BaseSchema):
    email: str | None = None
    full_name: str | None = None
    is_active: bool | None = None
    role_codes: list[str] | None = None
    page_acls: list[str] | None = None


class UserRead(IDTimestampSchema):
    username: str
    email: str | None
    full_name: str | None
    is_active: bool
    is_superuser: bool
    must_change_password: bool
    last_login_at: datetime | None
    role_codes: list[str]
    page_acls: list[str]


class RoleRead(IDTimestampSchema):
    code: str
    name: str
    description: str | None
    is_system: bool
    permission_codes: list[str]
