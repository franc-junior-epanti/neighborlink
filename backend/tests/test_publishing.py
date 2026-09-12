from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import schedules as schedules_api
from app.auth.cognito import Identity, get_current_identity
from app.database import get_db
from app.integrations.agent_runtime import LocalAgentRuntime
from app.main import app
from app.models import Base, Membership, NotificationOutbox, Organization, User


@pytest.fixture
def publishing_context() -> Generator[tuple[TestClient, Session, Organization], None, None]:
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
        organization = Organization(name="NeighborLink Douala", slug="publish-douala")
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


def _seed_and_generate(client: TestClient, organization: Organization) -> dict:
    demo = client.post(f"/api/v1/organizations/{organization.id}/demo")
    operation_id = demo.json()["operation_id"]
    generated = client.post(
        f"/api/v1/operations/{operation_id}/schedule-versions",
        json={"instruction": "Prépare le planning de Douala"},
    )
    assert generated.status_code == 201
    return generated.json()


def _consent_all_volunteers(db: Session) -> None:
    from app.models import Volunteer

    for volunteer in db.scalars(select(Volunteer)):
        volunteer.email_consent = True
    db.commit()


def test_publish_requires_matching_revision(publishing_context) -> None:
    client, db, organization = publishing_context
    version = _seed_and_generate(client, organization)
    _consent_all_volunteers(db)

    stale = client.post(
        f"/api/v1/schedule-versions/{version['id']}/publish",
        json={"expected_revision": version["revision"] + 1},
    )
    assert stale.status_code == 409
    assert db.scalar(select(NotificationOutbox)) is None


def test_publish_creates_outbox_rows_and_marks_version_published(publishing_context) -> None:
    client, db, organization = publishing_context
    version = _seed_and_generate(client, organization)
    _consent_all_volunteers(db)

    published = client.post(
        f"/api/v1/schedule-versions/{version['id']}/publish",
        json={"expected_revision": version["revision"]},
    )
    assert published.status_code == 200
    body = published.json()
    assert body["status"] == "published"
    assert body["approved_at"] is not None
    assert len(body["notifications"]) == len(version["assignments"])
    assert all(item["status"] == "pending" for item in body["notifications"])


def test_publish_twice_does_not_duplicate_notifications(publishing_context) -> None:
    client, db, organization = publishing_context
    version = _seed_and_generate(client, organization)
    _consent_all_volunteers(db)

    first = client.post(
        f"/api/v1/schedule-versions/{version['id']}/publish",
        json={"expected_revision": version["revision"]},
    )
    assert first.status_code == 200

    second = client.post(
        f"/api/v1/schedule-versions/{version['id']}/publish",
        json={"expected_revision": version["revision"]},
    )
    assert second.status_code == 409

    outbox_rows = list(db.scalars(select(NotificationOutbox)))
    assert len(outbox_rows) == len(first.json()["notifications"])


def test_dispatch_before_publish_is_rejected(publishing_context) -> None:
    client, db, organization = publishing_context
    version = _seed_and_generate(client, organization)
    _consent_all_volunteers(db)

    dispatched = client.post(
        f"/api/v1/schedule-versions/{version['id']}/notifications/dispatch"
    )
    assert dispatched.status_code == 409
    assert db.scalar(select(NotificationOutbox)) is None


def test_dispatch_marks_notifications_simulated(publishing_context) -> None:
    client, db, organization = publishing_context
    version = _seed_and_generate(client, organization)
    _consent_all_volunteers(db)

    client.post(
        f"/api/v1/schedule-versions/{version['id']}/publish",
        json={"expected_revision": version["revision"]},
    )
    dispatched = client.post(
        f"/api/v1/schedule-versions/{version['id']}/notifications/dispatch"
    )
    assert dispatched.status_code == 200
    notifications = dispatched.json()["notifications"]
    assert notifications
    assert all(item["status"] == "simulated" for item in notifications)
    assert all(item["attempt_count"] == 1 for item in notifications)


def test_dispatch_reports_partial_failure(publishing_context) -> None:
    client, db, organization = publishing_context
    version = _seed_and_generate(client, organization)
    _consent_all_volunteers(db)

    client.post(
        f"/api/v1/schedule-versions/{version['id']}/publish",
        json={"expected_revision": version["revision"]},
    )

    from app.api import publishing as publishing_api
    from app.services.publishing import dispatch_pending

    class FlakyAdapter:
        def __init__(self) -> None:
            self.calls = 0

        def send(self, outbox) -> bool:
            self.calls += 1
            return self.calls > 1

    def failing_dispatch(db_session, version_id, registry=None):
        flaky = FlakyAdapter()
        return dispatch_pending(
            db_session, version_id, registry={"email": flaky, "whatsapp": flaky}
        )

    original = publishing_api.dispatch_pending
    publishing_api.dispatch_pending = failing_dispatch
    try:
        dispatched = client.post(
            f"/api/v1/schedule-versions/{version['id']}/notifications/dispatch"
        )
    finally:
        publishing_api.dispatch_pending = original

    assert dispatched.status_code == 200
    statuses = {item["status"] for item in dispatched.json()["notifications"]}
    assert statuses == {"failed"} or "failed" in statuses


def test_preview_flags_volunteers_without_consent(publishing_context) -> None:
    client, db, organization = publishing_context
    version = _seed_and_generate(client, organization)

    from app.models import Volunteer

    for volunteer in db.scalars(select(Volunteer)):
        volunteer.email_consent = False
        volunteer.whatsapp_consent = False
    db.commit()

    preview = client.get(
        f"/api/v1/schedule-versions/{version['id']}/notifications/preview"
    )
    assert preview.status_code == 200
    assert all(item["blocked_reason"] is not None for item in preview.json())
    assert all(item["channel"] is None for item in preview.json())
