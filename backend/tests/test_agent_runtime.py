import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from agent.contracts import AgentRequest, AgentResponse
from agent.runtime import invoke
from app.integrations.agent_runtime import AgentCoreRuntime, LocalAgentRuntime
from app.optimizer import AvailabilityInput, ScheduleInput, ShiftInput, VolunteerInput
from app.schemas.jobs import CreateAgentJob
from app.services.jobs import AgentJobService, JobStore

START = datetime(2026, 9, 20, 8, tzinfo=UTC)


def request() -> AgentRequest:
    return AgentRequest(
        session_id=str(uuid4()),
        organization_id=str(uuid4()),
        operation_snapshot=ScheduleInput(
            volunteers=[
                VolunteerInput(
                    id="amina",
                    display_name="Amina",
                    skills={"distribution"},
                    availability=[
                        AvailabilityInput(
                            starts_at=START, ends_at=START + timedelta(hours=4)
                        )
                    ],
                )
            ],
            shifts=[
                ShiftInput(
                    id="shift",
                    name="Distribution",
                    role_name="Distribution",
                    required_skill="distribution",
                    starts_at=START,
                    ends_at=START + timedelta(hours=2),
                    capacity=1,
                )
            ],
        ),
    )


def test_local_and_agentcore_entrypoint_share_contract() -> None:
    payload = request()
    local = LocalAgentRuntime().invoke(payload)
    hosted = AgentResponse.model_validate(invoke(payload.model_dump(mode="json")))
    assert hosted.status == local.status == "proposal"
    assert hosted.schedule == local.schedule


def test_agentcore_adapter_decodes_stream_and_traces_session() -> None:
    expected = LocalAgentRuntime().invoke(request())

    class FakeClient:
        called_with = None

        def invoke_agent_runtime(self, **kwargs):
            self.called_with = kwargs
            body = json.dumps(expected.model_dump(mode="json")).encode()
            return {"response": [body[:20], body[20:]]}

    client = FakeClient()
    payload = request()
    result = AgentCoreRuntime("arn:runtime", client=client).invoke(payload)
    assert result == expected
    assert client.called_with["runtimeSessionId"] == payload.session_id
    assert json.loads(client.called_with["payload"])["request_id"] == payload.request_id


def test_job_tracks_all_stages() -> None:
    store = JobStore()
    service = AgentJobService(store, LocalAgentRuntime())
    payload = CreateAgentJob(request=request())
    job = service.submit(payload)
    service.run(job.id, payload)
    completed = store.get(job.id)
    assert completed is not None
    assert completed.status == "completed"
    assert completed.progress == [
        "queued",
        "analyzing",
        "optimizing",
        "verifying",
        "explaining",
        "completed",
    ]
    assert completed.request_id == payload.request.request_id


def test_runtime_failure_keeps_last_draft_reference() -> None:
    class FailingRuntime:
        def invoke(self, _request):
            raise RuntimeError("runtime unavailable")

    draft_id = uuid4()
    store = JobStore()
    service = AgentJobService(store, FailingRuntime())
    payload = CreateAgentJob(request=request(), last_draft_id=draft_id)
    job = service.submit(payload)
    service.run(job.id, payload)
    failed = store.get(job.id)
    assert failed is not None
    assert failed.status == "failed"
    assert failed.last_draft_id == draft_id
    assert "runtime unavailable" in failed.error
