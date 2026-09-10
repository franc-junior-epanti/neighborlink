from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from app.optimizer.schemas import ScheduleInput, ScheduleResult


class AgentRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    organization_id: str
    operation_snapshot: ScheduleInput
    instruction: str | None = None


class ToolCallRecord(BaseModel):
    tool: Literal["optimize_schedule", "validate_plan", "explain_plan"]
    status: Literal["started", "completed", "failed"]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AgentResponse(BaseModel):
    status: Literal["proposal", "needs_clarification", "infeasible"]
    schedule: ScheduleResult | None = None
    explanations: list[str] = Field(default_factory=list)
    clarification_question: str | None = None
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
