from datetime import UTC, datetime, timedelta

from agent.contracts import AgentRequest
from agent.neighborlink import LocalNeighborLinkWorkflow, build_strands_agent
from agent.tools.validate_plan import run_validation
from app.optimizer import AvailabilityInput, ScheduleInput, ShiftInput, VolunteerInput

START = datetime(2026, 9, 20, 8, tzinfo=UTC)


def snapshot() -> ScheduleInput:
    return ScheduleInput(
        volunteers=[
            VolunteerInput(
                id="amina",
                display_name="Amina",
                skills={"distribution"},
                availability=[
                    AvailabilityInput(starts_at=START, ends_at=START + timedelta(hours=4))
                ],
            )
        ],
        shifts=[
            ShiftInput(
                id="distribution",
                name="Distribution matin",
                role_name="Distribution",
                required_skill="distribution",
                starts_at=START,
                ends_at=START + timedelta(hours=2),
                capacity=1,
            )
        ],
    )


def request(instruction: str | None = None) -> AgentRequest:
    return AgentRequest(
        session_id="operation:demo",
        organization_id="neighborlink-douala",
        operation_snapshot=snapshot(),
        instruction=instruction,
    )


def test_local_workflow_uses_solver_validator_and_explainer() -> None:
    result = LocalNeighborLinkWorkflow().run(request())
    assert result.status == "proposal"
    assert result.schedule is not None
    assert result.schedule.assignments[0].volunteer_id == "amina"
    assert [call.tool for call in result.tool_calls if call.status == "completed"] == [
        "optimize_schedule",
        "validate_plan",
        "explain_plan",
    ]
    assert result.explanations[0].startswith("Amina → Distribution matin")


def test_ambiguous_instruction_requests_clarification_without_tools() -> None:
    result = LocalNeighborLinkWorkflow().run(request("Remplace-le dans le planning"))
    assert result.status == "needs_clarification"
    assert result.clarification_question is not None
    assert result.tool_calls == []


def test_independent_validator_rejects_invented_assignment() -> None:
    proposed = {
        "status": "complete",
        "assignments": [
            {
                "volunteer_id": "inconnu",
                "shift_id": "distribution",
                "reason_codes": ["available"],
            }
        ],
        "uncovered_requirements": [],
        "score": {"total": 1},
    }
    result = run_validation(snapshot().model_dump(mode="json"), proposed)
    assert result["valid"] is False
    assert result["violations"][0].startswith("unknown_reference")


def test_strands_agent_exposes_only_three_safe_tools() -> None:
    # Construction is enough here: no external model invocation during unit tests.
    agent = build_strands_agent()
    assert set(agent.tool_names) == {"optimize_schedule", "validate_plan", "explain_plan"}
