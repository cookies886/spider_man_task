import uuid
from datetime import datetime

from pydantic import Field

from app.models.alert import AlertSendStatus, ConditionType
from app.schemas.base import BaseSchema, IDTimestampSchema


class AlertRuleCreate(BaseSchema):
    project_id: uuid.UUID | None = None
    name: str = Field(max_length=128)
    condition_type: ConditionType
    threshold: int = Field(default=1, ge=1)
    channels: dict
    enabled: bool = True


class AlertRuleUpdate(BaseSchema):
    name: str | None = Field(default=None, max_length=128)
    condition_type: ConditionType | None = None
    threshold: int | None = Field(default=None, ge=1)
    channels: dict | None = None
    enabled: bool | None = None


class AlertRuleRead(IDTimestampSchema):
    project_id: uuid.UUID | None
    name: str
    condition_type: ConditionType
    threshold: int
    channels: dict
    enabled: bool


class AlertHistoryRead(IDTimestampSchema):
    rule_id: uuid.UUID
    task_id: uuid.UUID | None
    worker_id: uuid.UUID | None
    message: str
    channel: str
    sent_at: datetime
    status: AlertSendStatus
