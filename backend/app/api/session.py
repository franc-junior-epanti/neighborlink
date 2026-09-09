from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.cognito import Identity, get_current_identity
from app.database import get_db
from app.repositories.session import get_membership, list_memberships, synchronize_user
from app.schemas.session import (
    ActiveOrganizationRequest,
    ActiveOrganizationResponse,
    OrganizationSummary,
    SessionResponse,
)

router = APIRouter(prefix="/api/v1", tags=["session"])
CurrentIdentity = Annotated[Identity, Depends(get_current_identity)]
DatabaseSession = Annotated[Session, Depends(get_db)]


def to_summary(membership, organization) -> OrganizationSummary:
    return OrganizationSummary(
        id=organization.id,
        name=organization.name,
        slug=organization.slug,
        role=membership.role,
    )


@router.get("/me", response_model=SessionResponse)
def read_session(
    identity: CurrentIdentity,
    db: DatabaseSession,
) -> SessionResponse:
    user = synchronize_user(db, identity)
    organizations = [to_summary(*row) for row in list_memberships(db, user.id)]
    return SessionResponse(
        user_id=user.id,
        display_name=user.display_name,
        email=user.email,
        organizations=organizations,
    )


@router.post("/session/active-organization", response_model=ActiveOrganizationResponse)
def validate_active_organization(
    payload: ActiveOrganizationRequest,
    identity: CurrentIdentity,
    db: DatabaseSession,
) -> ActiveOrganizationResponse:
    user = synchronize_user(db, identity)
    row = get_membership(db, user.id, payload.organization_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this organization",
        )
    return ActiveOrganizationResponse(organization=to_summary(*row))
