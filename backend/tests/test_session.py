from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.cognito import Identity, get_current_identity
from app.database import get_db
from app.main import app
from app.models import Base, Membership, Organization, User


@pytest.fixture
def db() -> Generator[Session, None, None]:
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
    local_session = sessionmaker(bind=engine, expire_on_commit=False)
    with local_session() as session:
        yield session


@pytest.fixture
def client(db: Session) -> Generator[TestClient, None, None]:
    def override_db() -> Generator[Session, None, None]:
        yield db

    def override_identity() -> Identity:
        return Identity(
            subject="cognito-owner",
            email="owner@example.test",
            display_name="Owner",
        )

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_identity] = override_identity
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def seed_access(db: Session) -> tuple[Organization, Organization]:
    allowed = Organization(name="Allowed", slug="allowed")
    forbidden = Organization(name="Forbidden", slug="forbidden")
    user = User(
        cognito_sub="cognito-owner",
        email="owner@example.test",
        display_name="Owner",
    )
    db.add_all([allowed, forbidden, user])
    db.flush()
    db.add(Membership(user_id=user.id, organization_id=allowed.id, role="coordinator"))
    db.commit()
    return allowed, forbidden


def test_me_requires_authentication() -> None:
    app.dependency_overrides.clear()
    with TestClient(app) as anonymous_client:
        response = anonymous_client.get("/api/v1/me")
    assert response.status_code == 401


def test_me_lists_only_accessible_organizations(client: TestClient, db: Session) -> None:
    allowed, _ = seed_access(db)

    response = client.get("/api/v1/me")

    assert response.status_code == 200
    assert response.json()["organizations"] == [
        {"id": str(allowed.id), "name": "Allowed", "slug": "allowed", "role": "coordinator"}
    ]


def test_active_organization_rejects_cross_tenant_access(
    client: TestClient, db: Session
) -> None:
    _, forbidden = seed_access(db)

    response = client.post(
        "/api/v1/session/active-organization",
        json={"organization_id": str(forbidden.id)},
    )

    assert response.status_code == 403
