import json
from typing import Protocol

import boto3

from agent.contracts import AgentRequest, AgentResponse
from agent.neighborlink import LocalNeighborLinkWorkflow
from app.config import get_settings


class AgentRuntime(Protocol):
    def invoke(self, request: AgentRequest) -> AgentResponse: ...


class LocalAgentRuntime:
    def __init__(self, workflow: LocalNeighborLinkWorkflow | None = None) -> None:
        self.workflow = workflow or LocalNeighborLinkWorkflow()

    def invoke(self, request: AgentRequest) -> AgentResponse:
        return self.workflow.run(request)


class AgentCoreRuntime:
    def __init__(
        self,
        runtime_arn: str,
        qualifier: str = "DEFAULT",
        client=None,
        region_name: str | None = None,
    ) -> None:
        self.runtime_arn = runtime_arn
        self.qualifier = qualifier
        self.client = client or boto3.client("bedrock-agentcore", region_name=region_name)

    def invoke(self, request: AgentRequest) -> AgentResponse:
        response = self.client.invoke_agent_runtime(
            agentRuntimeArn=self.runtime_arn,
            runtimeSessionId=request.session_id,
            qualifier=self.qualifier,
            payload=request.model_dump_json().encode(),
        )
        chunks = response.get("response", [])
        raw = b"".join(chunk if isinstance(chunk, bytes) else chunk.read() for chunk in chunks)
        return AgentResponse.model_validate(json.loads(raw.decode()))


def configured_runtime() -> AgentRuntime:
    settings = get_settings()
    if settings.agent_runtime_mode == "agentcore":
        if not settings.agent_runtime_arn:
            raise RuntimeError("AGENT_RUNTIME_ARN est requis en mode agentcore")
        return AgentCoreRuntime(
            settings.agent_runtime_arn,
            settings.agent_runtime_qualifier,
            region_name=settings.aws_region,
        )
    return LocalAgentRuntime()
