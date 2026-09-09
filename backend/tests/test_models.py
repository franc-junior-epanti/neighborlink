from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models import Base, Membership, Operation, Organization, User, Volunteer


@pytest.fixture
def session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session


def test_same_email_is_allowed_in_two_organizations(session: Session) -> None:
    first = Organization(name="Association A", slug="association-a")
    second = Organization(name="Association B", slug="association-b")
    session.add_all([first, second])
    session.flush()
    session.add_all(
        [
            Volunteer(
                organization_id=first.id,
                display_name="Amina",
                email="amina@example.test",
            ),
            Volunteer(
                organization_id=second.id,
                display_name="Amina",
                email="amina@example.test",
            ),
        ]
    )
    session.commit()

    assert session.query(Volunteer).count() == 2


def test_duplicate_membership_is_rejected(session: Session) -> None:
    organization = Organization(name="Association", slug="association")
    user = User(cognito_sub="cognito-user", email="owner@example.test", display_name="Owner")
    session.add_all([organization, user])
    session.flush()
    session.add_all(
        [
            Membership(user_id=user.id, organization_id=organization.id),
            Membership(user_id=user.id, organization_id=organization.id),
        ]
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_orphan_operation_is_rejected(session: Session) -> None:
    session.add(
        Operation(
            organization_id=uuid4(),
            name="Orphan operation",
            event_date=date(2026, 9, 10),
            location_name="Douala",
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()
