from datetime import UTC, datetime
from threading import Lock
from uuid import UUID

from app.integrations.agent_runtime import AgentRuntime
from app.schemas.jobs import AgentJob, CreateAgentJob, JobStage


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[UUID, AgentJob] = {}
        self._lock = Lock()

    def create(self, payload: CreateAgentJob) -> AgentJob:
        job = AgentJob(
            request_id=payload.request.request_id,
            session_id=payload.request.session_id,
            organization_id=payload.request.organization_id,
            last_draft_id=payload.last_draft_id,
        )
        with self._lock:
            self._jobs[job.id] = job
        return job.model_copy(deep=True)

    def get(self, job_id: UUID) -> AgentJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return job.model_copy(deep=True) if job else None

    def update(self, job_id: UUID, status: JobStage) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = status
            if job.progress[-1] != status:
                job.progress.append(status)
            job.updated_at = datetime.now(UTC)

    def complete(self, job_id: UUID, result) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.result = result
            job.status = "completed"
            job.progress.append("completed")
            job.updated_at = datetime.now(UTC)

    def fail(self, job_id: UUID, error: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.error = error
            job.status = "failed"
            job.progress.append("failed")
            job.updated_at = datetime.now(UTC)


class AgentJobService:
    def __init__(self, store: JobStore, runtime: AgentRuntime) -> None:
        self.store = store
        self.runtime = runtime

    def submit(self, payload: CreateAgentJob) -> AgentJob:
        return self.store.create(payload)

    def run(self, job_id: UUID, payload: CreateAgentJob) -> None:
        try:
            for stage in ("analyzing", "optimizing", "verifying", "explaining"):
                self.store.update(job_id, stage)
            self.store.complete(job_id, self.runtime.invoke(payload.request))
        except (RuntimeError, ValueError) as exc:
            self.store.fail(job_id, f"{type(exc).__name__}: {exc}")
