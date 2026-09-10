from bedrock_agentcore import BedrockAgentCoreApp

from agent.contracts import AgentRequest
from agent.neighborlink import LocalNeighborLinkWorkflow

app = BedrockAgentCoreApp()
workflow = LocalNeighborLinkWorkflow()


@app.entrypoint
def invoke(payload: dict) -> dict:
    """Point d'entrée HTTP portable pour AgentCore Runtime."""
    request = AgentRequest.model_validate(payload)
    return workflow.run(request).model_dump(mode="json")


if __name__ == "__main__":
    app.run()
