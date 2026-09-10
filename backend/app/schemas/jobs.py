from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from agent.contracts import AgentRequest, AgentResponse

JobStage = Literal[
    "queued", "analyzing", "optimizing", "verifying", "explaining", "completed", "failed"
]


class CreateAgentJob(BaseModel):
    request: AgentRequest
    last_draft_id: UUID | None = None


class AgentJob(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    request_id: str
    session_id: str
    organization_id: str
    status: JobStage = "queued"
    progress: list[JobStage] = Field(default_factory=lambda: ["queued"])
    result: AgentResponse | None = None
    error: str | None = None
    last_draft_id: UUID | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
