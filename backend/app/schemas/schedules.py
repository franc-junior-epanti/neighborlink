from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class OperationSummary(BaseModel):
    id: UUID
    name: str
    event_date: date
    location_name: str
    status: str


class GenerateScheduleRequest(BaseModel):
    instruction: str | None = Field(default=None, max_length=1000)
    base_version_id: UUID | None = None


class ManualMoveRequest(BaseModel):
    volunteer_id: UUID
    to_shift_id: UUID
    from_shift_id: UUID | None = None


class AssignmentView(BaseModel):
    id: UUID
    volunteer_id: UUID
    volunteer_name: str
    shift_id: UUID
    shift_name: str
    starts_at: datetime
    ends_at: datetime
    response_status: str
    reason_codes: list[str] = Field(default_factory=list)
    distance_km: float | None = None


class ShiftView(BaseModel):
    id: UUID
    name: str
    role_name: str
    starts_at: datetime
    ends_at: datetime
    capacity: int


class ScheduleVersionSummary(BaseModel):
    id: UUID
    revision: int
    status: str
    origin: str
    total_score: int
    created_at: datetime


class ToolCallView(BaseModel):
    tool: str
    status: str
    timestamp: datetime


class ScheduleVersionDetail(ScheduleVersionSummary):
    operation_id: UUID
    score_details: dict[str, int]
    conflicts: list[str]
    explanations: list[str]
    assignments: list[AssignmentView]
    shifts: list[ShiftView]
    agent_session_id: str | None = None
    agent_request_id: str | None = None
    tool_calls: list[ToolCallView] = Field(default_factory=list)


class ScheduleDiff(BaseModel):
    base_version_id: UUID | None
    target_version_id: UUID
    added: list[str]
    removed: list[str]

