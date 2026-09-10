import re

from strands import Agent

from agent.contracts import AgentRequest, AgentResponse, ToolCallRecord
from agent.tools import explain_plan, optimize_schedule, validate_plan
from agent.tools.explain_plan import run_explanation
from agent.tools.optimize_schedule import run_optimizer
from agent.tools.validate_plan import run_validation
from app.optimizer import ScheduleResult

SYSTEM_PROMPT = """Tu es l'orchestrateur NeighborLink. Tu dois utiliser optimize_schedule pour
calculer toute affectation, validate_plan pour contrôler les contraintes, puis explain_plan pour
expliquer uniquement les faits retournés. Tu ne peux ni accéder à SQL, ni envoyer de message, ni
publier un planning. Si une instruction de modification ne précise pas la personne ou le poste,
demande une clarification."""


def build_strands_agent(model=None) -> Agent:
    options = {"tools": [optimize_schedule, validate_plan, explain_plan], "system_prompt": SYSTEM_PROMPT}
    if model is not None:
        options["model"] = model
    return Agent(**options)


def _ambiguous(instruction: str | None) -> bool:
    if not instruction:
        return False
    normalized = instruction.strip().casefold()
    requests_change = any(word in normalized for word in ("remplace", "change", "déplace", "modifie"))
    named_words = re.findall(r"\b[A-ZÀ-ÖØ-Ý][a-zà-öø-ÿ]+\b", instruction)
    has_specific_target = len(named_words) > 1
    return requests_change and not has_specific_target


class LocalNeighborLinkWorkflow:
    """Chemin local reproductible utilisant exactement les mêmes implémentations que les outils Strands."""

    def run(self, request: AgentRequest) -> AgentResponse:
        if _ambiguous(request.instruction):
            return AgentResponse(
                status="needs_clarification",
                clarification_question="Quelle personne ou quel poste faut-il modifier ?",
            )
        journal: list[ToolCallRecord] = []
        payload = request.operation_snapshot.model_dump(mode="json")
        journal.append(ToolCallRecord(tool="optimize_schedule", status="started"))
        proposed = run_optimizer(payload)
        journal.append(ToolCallRecord(tool="optimize_schedule", status="completed"))
        journal.append(ToolCallRecord(tool="validate_plan", status="started"))
        validation = run_validation(payload, proposed)
        journal.append(ToolCallRecord(tool="validate_plan", status="completed"))
        if not validation["valid"]:
            schedule = ScheduleResult.model_validate(proposed)
            schedule.hard_constraint_violations = validation["violations"]
            return AgentResponse(status="infeasible", schedule=schedule, tool_calls=journal)
        journal.append(ToolCallRecord(tool="explain_plan", status="started"))
        explanation = run_explanation(payload, proposed)
        journal.append(ToolCallRecord(tool="explain_plan", status="completed"))
        schedule = ScheduleResult.model_validate(proposed)
        return AgentResponse(
            status="proposal" if schedule.assignments else "infeasible",
            schedule=schedule,
            explanations=explanation["facts"],
            tool_calls=journal,
        )
