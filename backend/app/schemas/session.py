from uuid import UUID

from pydantic import BaseModel, ConfigDict


class OrganizationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    role: str


class SessionResponse(BaseModel):
    user_id: UUID
    display_name: str
    email: str
    organizations: list[OrganizationSummary]


class ActiveOrganizationRequest(BaseModel):
    organization_id: UUID


class ActiveOrganizationResponse(BaseModel):
    organization: OrganizationSummary
