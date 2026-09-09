from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.cognito import Identity
from app.models import Membership, Organization, User


def synchronize_user(db: Session, identity: Identity) -> User:
    user = db.scalar(select(User).where(User.cognito_sub == identity.subject))
    if user is None:
        user = User(
            cognito_sub=identity.subject,
            email=identity.email or f"{identity.subject}@unknown.invalid",
            display_name=identity.display_name,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    elif identity.email and (user.email != identity.email or user.display_name != identity.display_name):
        user.email = identity.email
        user.display_name = identity.display_name
        db.commit()
        db.refresh(user)
    return user


def list_memberships(db: Session, user_id: UUID) -> list[tuple[Membership, Organization]]:
    statement = (
        select(Membership, Organization)
        .join(Organization, Organization.id == Membership.organization_id)
        .where(Membership.user_id == user_id)
        .order_by(Organization.name)
    )
    return list(db.execute(statement).tuples())


def get_membership(
    db: Session, user_id: UUID, organization_id: UUID
) -> tuple[Membership, Organization] | None:
    statement = (
        select(Membership, Organization)
        .join(Organization, Organization.id == Membership.organization_id)
        .where(
            Membership.user_id == user_id,
            Membership.organization_id == organization_id,
        )
    )
    return db.execute(statement).tuples().one_or_none()
