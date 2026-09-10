from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from app.api.session import CurrentIdentity, DatabaseSession
from app.integrations.agent_runtime import configured_runtime
from app.repositories.session import get_membership, synchronize_user
from app.schemas.jobs import AgentJob, CreateAgentJob
from app.services.jobs import AgentJobService, JobStore

router = APIRouter(prefix="/api/v1/agent/jobs", tags=["agent-jobs"])
store = JobStore()


def _authorize_organization(
    organization_id: str, identity: CurrentIdentity, db: DatabaseSession
) -> None:
    user = synchronize_user(db, identity)
    try:
        parsed = UUID(organization_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="organization_id invalide") from exc
    if get_membership(db, user.id, parsed) is None:
        raise HTTPException(status_code=403, detail="Association interdite")


@router.post("", response_model=AgentJob, status_code=status.HTTP_202_ACCEPTED)
def create_job(
    payload: CreateAgentJob,
    background_tasks: BackgroundTasks,
    identity: CurrentIdentity,
    db: DatabaseSession,
) -> AgentJob:
    _authorize_organization(payload.request.organization_id, identity, db)
    service = AgentJobService(store, configured_runtime())
    job = service.submit(payload)
    background_tasks.add_task(service.run, job.id, payload)
    return job


@router.get("/{job_id}", response_model=AgentJob)
def read_job(job_id: UUID, identity: CurrentIdentity, db: DatabaseSession) -> AgentJob:
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job introuvable")
    _authorize_organization(job.organization_id, identity, db)
    return job
