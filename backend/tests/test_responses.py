from collections.abc import Generator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import schedules as schedules_api
from app.auth.cognito import Identity, get_current_identity
from app.config import get_settings
from app.database import get_db
from app.integrations.agent_runtime import LocalAgentRuntime
from app.main import app
from app.models import Assignment, Base, Membership, Organization, User, Volunteer
from app.services.responses import sign_response_token


@pytest.fixture
def responses_context() -> Generator[tuple[TestClient, Session, Organization], None, None]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    local_session = sessionmaker(bind=engine, expire_on_commit=False)
    with local_session() as db:
        organization = Organization(name="NeighborLink Douala", slug="responses-douala")
        user = User(cognito_sub="planner", email="planner@test.dev", display_name="Planner")
        db.add_all([organization, user])
        db.flush()
        db.add(Membership(user_id=user.id, organization_id=organization.id, role="coordinator"))
        db.commit()

        def override_db():
            yield db

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_identity] = lambda: Identity(
            subject="planner", email="planner@test.dev", display_name="Planner"
        )
        original_runtime = schedules_api.configured_runtime
        schedules_api.configured_runtime = lambda: LocalAgentRuntime()
        with TestClient(app) as client:
            yield client, db, organization
        schedules_api.configured_runtime = original_runtime
        app.dependency_overrides.clear()


def _seed_assignment(client: TestClient, db: Session, organization: Organization) -> Assignment:
    demo = client.post(f"/api/v1/organizations/{organization.id}/demo")
    operation_id = demo.json()["operation_id"]
    generated = client.post(
        f"/api/v1/operations/{operation_id}/schedule-versions",
        json={"instruction": "Prépare le planning de Douala"},
    )
    assert generated.status_code == 201
    for volunteer in db.scalars(select(Volunteer)):
        volunteer.email_consent = True
    db.commit()
    assignment = db.scalars(select(Assignment)).first()
    assert assignment is not None
    return assignment


def test_confirm_link_marks_assignment_confirmed(responses_context) -> None:
    client, db, organization = responses_context
    assignment = _seed_assignment(client, db, organization)
    secret = get_settings().response_signing_secret
    token = sign_response_token(secret, assignment.id, "confirm")

    response = client.get(f"/api/v1/public/responses/{token}")

    assert response.status_code == 200
    assert "confirmée" in response.text
    db.refresh(assignment)
    assert assignment.response_status == "confirmed"


def test_decline_link_marks_assignment_declined(responses_context) -> None:
    client, db, organization = responses_context
    assignment = _seed_assignment(client, db, organization)
    secret = get_settings().response_signing_secret
    token = sign_response_token(secret, assignment.id, "decline")

    response = client.get(f"/api/v1/public/responses/{token}")

    assert response.status_code == 200
    assert "enregistrée" in response.text
    db.refresh(assignment)
    assert assignment.response_status == "declined"


def test_response_link_is_idempotent_on_replay(responses_context) -> None:
    client, db, organization = responses_context
    assignment = _seed_assignment(client, db, organization)
    secret = get_settings().response_signing_secret
    token = sign_response_token(secret, assignment.id, "confirm")

    first = client.get(f"/api/v1/public/responses/{token}")
    second = client.get(f"/api/v1/public/responses/{token}")

    assert first.status_code == second.status_code == 200
    from app.models import VolunteerResponse

    count = len(
        list(db.scalars(select(VolunteerResponse).where(VolunteerResponse.assignment_id == assignment.id)))
    )
    assert count == 1


def test_tampered_token_is_rejected(responses_context) -> None:
    client, db, organization = responses_context
    assignment = _seed_assignment(client, db, organization)
    secret = get_settings().response_signing_secret
    token = sign_response_token(secret, assignment.id, "confirm")
    tampered = token[:-4] + "abcd"

    response = client.get(f"/api/v1/public/responses/{tampered}")

    assert response.status_code == 200
    assert "invalide" in response.text
    db.refresh(assignment)
    assert assignment.response_status != "confirmed"


def test_unknown_assignment_is_rejected(responses_context) -> None:
    client, _db, _organization = responses_context
    secret = get_settings().response_signing_secret
    token = sign_response_token(secret, uuid4(), "confirm")

    response = client.get(f"/api/v1/public/responses/{token}")

    assert response.status_code == 200
    assert "invalide" in response.text
