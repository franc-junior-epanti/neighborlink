from collections.abc import Generator
from uuid import UUID

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
from app.models import Base, Membership, Organization, ScheduleVersion, User


@pytest.fixture
def schedule_context() -> Generator[tuple[TestClient, Session, Organization], None, None]:
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
        organization = Organization(name="NeighborLink Douala", slug="schedule-douala")
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


def test_generation_persists_distinct_draft_versions(schedule_context) -> None:
    client, _, organization = schedule_context
    first = _seed_and_generate(client, organization)
    second = client.post(
        f"/api/v1/operations/{first['operation_id']}/schedule-versions",
        json={"instruction": "Propose une nouvelle version"},
    )
    assert second.status_code == 201
    assert second.json()["id"] != first["id"]
    assert second.json()["revision"] == 2
    versions = client.get(
        f"/api/v1/operations/{first['operation_id']}/schedule-versions"
    ).json()
    assert [item["revision"] for item in versions] == [2, 1]


def test_generation_persists_agent_tool_call_journal(schedule_context) -> None:
    client, _, organization = schedule_context
    generated = _seed_and_generate(client, organization)
    assert generated["agent_session_id"] == generated["operation_id"]
    assert generated["agent_request_id"]
    tools = [call["tool"] for call in generated["tool_calls"]]
    assert tools == [
        "optimize_schedule",
        "optimize_schedule",
        "validate_plan",
        "validate_plan",
        "explain_plan",
        "explain_plan",
    ]
    statuses = [call["status"] for call in generated["tool_calls"]]
    assert statuses == ["started", "completed"] * 3

    fetched = client.get(
        f"/api/v1/operations/{generated['operation_id']}/schedule-versions/{generated['id']}"
    )
    assert fetched.json()["tool_calls"] == generated["tool_calls"]


def test_manual_move_creates_version_without_agent_journal(schedule_context) -> None:
    client, _, organization = schedule_context
    base = _seed_and_generate(client, organization)
    assignment = base["assignments"][0]
    moved = client.post(
        f"/api/v1/schedule-versions/{base['id']}/manual-moves",
        json={
            "volunteer_id": assignment["volunteer_id"],
            "from_shift_id": assignment["shift_id"],
            "to_shift_id": assignment["shift_id"],
        },
    )
    assert moved.json()["tool_calls"] == []
    assert moved.json()["agent_request_id"] is None


def test_manual_move_copies_published_version_without_mutating_it(schedule_context) -> None:
    client, db, organization = schedule_context
    base = _seed_and_generate(client, organization)
    persisted = db.get(ScheduleVersion, UUID(base["id"]))
    persisted.status = "published"
    db.commit()
    assignment = base["assignments"][0]
    moved = client.post(
        f"/api/v1/schedule-versions/{base['id']}/manual-moves",
        json={
            "volunteer_id": assignment["volunteer_id"],
            "from_shift_id": assignment["shift_id"],
            "to_shift_id": assignment["shift_id"],
        },
    )
    assert moved.status_code == 201
    assert moved.json()["status"] == "draft"
    assert moved.json()["origin"] == "manual"
    assert db.get(ScheduleVersion, UUID(base["id"])).status == "published"


def test_impossible_move_returns_conflict_and_creates_no_version(schedule_context) -> None:
    client, db, organization = schedule_context
    base = _seed_and_generate(client, organization)
    assignment = base["assignments"][0]
    incompatible = next(
        shift for shift in base["shifts"] if shift["id"] != assignment["shift_id"]
    )
    before = len(list(db.scalars(select(ScheduleVersion))))
    response = client.post(
        f"/api/v1/schedule-versions/{base['id']}/manual-moves",
        json={
            "volunteer_id": assignment["volunteer_id"],
            "from_shift_id": assignment["shift_id"],
            "to_shift_id": incompatible["id"],
        },
    )
    assert response.status_code == 409
    assert len(list(db.scalars(select(ScheduleVersion)))) == before


def test_diff_reports_added_and_removed_assignments(schedule_context) -> None:
    client, _, organization = schedule_context
    base = _seed_and_generate(client, organization)
    assignment = base["assignments"][0]
    moved = client.post(
        f"/api/v1/schedule-versions/{base['id']}/manual-moves",
        json={
            "volunteer_id": assignment["volunteer_id"],
            "from_shift_id": assignment["shift_id"],
            "to_shift_id": assignment["shift_id"],
        },
    ).json()
    diff = client.get(
        f"/api/v1/schedule-versions/{moved['id']}/diff?against={base['id']}"
    )
    assert diff.status_code == 200
    assert diff.json()["base_version_id"] == base["id"]
