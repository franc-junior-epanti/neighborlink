from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.cognito import Identity, get_current_identity
from app.database import get_db
from app.main import app
from app.models import Base, Membership, Organization, User, Volunteer


@pytest.fixture
def import_context() -> Generator[tuple[TestClient, Session, Organization], None, None]:
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
        organization = Organization(name="NeighborLink Douala", slug="neighborlink-douala")
        user = User(cognito_sub="importer", email="owner@test.dev", display_name="Owner")
        db.add_all([organization, user])
        db.flush()
        db.add(Membership(user_id=user.id, organization_id=organization.id, role="coordinator"))
        db.commit()

        def override_db():
            yield db

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_identity] = lambda: Identity(
            subject="importer", email="owner@test.dev", display_name="Owner"
        )
        with TestClient(app) as client:
            yield client, db, organization
        app.dependency_overrides.clear()


def preview(client: TestClient, organization: Organization, csv_text: str):
    return client.post(
        f"/api/v1/organizations/{organization.id}/imports/volunteers/preview",
        files={"file": ("volunteers.csv", csv_text.encode(), "text/csv")},
    )


def test_valid_csv_waits_for_confirmation(import_context) -> None:
    client, db, organization = import_context
    response = preview(
        client,
        organization,
        "display_name,email,skills\nAmina,amina@example.test,accueil|distribution\n",
    )
    assert response.status_code == 200
    assert response.json()["can_commit"] is True
    assert db.scalar(select(func.count()).select_from(Volunteer)) == 0

    committed = client.post(
        f"/api/v1/organizations/{organization.id}/imports/{response.json()['import_id']}/commit"
    )
    assert committed.status_code == 200
    assert committed.json()["imported"] == 1


def test_empty_csv_is_rejected(import_context) -> None:
    client, _, organization = import_context
    response = preview(client, organization, "")
    assert response.status_code == 422
    assert "vide" in response.json()["detail"]


def test_duplicate_csv_reports_line_and_blocks_commit(import_context) -> None:
    client, db, organization = import_context
    response = preview(
        client,
        organization,
        "display_name,email,skills\nA,a@example.test,accueil\nB,a@example.test,logistique\n",
    )
    body = response.json()
    assert body["can_commit"] is False
    assert body["errors"][0]["row"] == 3
    committed = client.post(
        f"/api/v1/organizations/{organization.id}/imports/{body['import_id']}/commit"
    )
    assert committed.status_code == 409
    assert db.scalar(select(func.count()).select_from(Volunteer)) == 0


def test_invalid_email_can_be_corrected(import_context) -> None:
    client, _, organization = import_context
    response = preview(
        client,
        organization,
        "display_name,email,skills\nAmina,pas-un-email,accueil\n",
    )
    body = response.json()
    assert body["errors"][0] == {"row": 2, "field": "email", "message": "Courriel invalide"}
    row = {**body["rows"][0], "email": "amina@example.test"}
    corrected = client.patch(
        f"/api/v1/organizations/{organization.id}/imports/{body['import_id']}/rows/2",
        json=row,
    )
    assert corrected.status_code == 200
    assert corrected.json()["can_commit"] is True


def test_demo_seed_is_idempotent(import_context) -> None:
    client, _, organization = import_context
    first = client.post(f"/api/v1/organizations/{organization.id}/demo")
    second = client.post(f"/api/v1/organizations/{organization.id}/demo")
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["volunteers"] == 12
    assert len(second.json()["roles"]) == 4
