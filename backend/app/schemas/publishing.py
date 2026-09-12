from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class NotificationPreviewItem(BaseModel):
    assignment_id: UUID
    volunteer_id: UUID
    volunteer_name: str
    channel: str | None
    recipient: str | None
    content: str
    blocked_reason: str | None = None


class PublishRequest(BaseModel):
    expected_revision: int


class OutboxStatusView(BaseModel):
    id: UUID
    assignment_id: UUID
    channel: str
    recipient: str
    mode: str
    status: str
    attempt_count: int
    last_error: str | None


class PublishResult(BaseModel):
    schedule_version_id: UUID
    status: str
    approved_at: datetime | None
    notifications: list[OutboxStatusView] = Field(default_factory=list)


class DispatchResult(BaseModel):
    notifications: list[OutboxStatusView]
