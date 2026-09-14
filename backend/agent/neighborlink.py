import re
from typing import Protocol

from pydantic import BaseModel, Field
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

INTERPRETER_SYSTEM_PROMPT = """Tu interprètes une instruction en français donnée par un
coordinateur bénévole au sujet d'un planning à calculer. Tu ne calcules rien toi-même et tu ne
choisis aucune affectation, tu ne fais que produire une décision structurée :
- Si l'instruction demande un changement ciblé (remplacer/déplacer/modifier) sans préciser
  clairement la personne ou le poste concerné, needs_clarification=true et pose une question
  précise dans clarification_question.
- Si l'instruction exprime une préférence de proximité (ex: "privilégie les bénévoles proches",
  "réduis les distances", "priorise la proximité"), fixe proximity_weight_multiplier entre 1.5 et
  3.0 selon l'intensité exprimée par le texte.
- Sinon, needs_clarification=false et proximity_weight_multiplier=1.0."""


def build_strands_agent(model=None) -> Agent:
    options = {"tools": [optimize_schedule, validate_plan, explain_plan], "system_prompt": SYSTEM_PROMPT}
    if model is not None:
        options["model"] = model
    return Agent(**options)


def build_instruction_interpreter(model=None) -> Agent:
    options = {"tools": [], "system_prompt": INTERPRETER_SYSTEM_PROMPT}
    if model is not None:
        options["model"] = model
    return Agent(**options)


class InstructionDecision(BaseModel):
    needs_clarification: bool = False
    clarification_question: str | None = None
    proximity_weight_multiplier: float = Field(default=1.0, ge=1.0, le=5.0)


def _ambiguous(instruction: str | None) -> bool:
    if not instruction:
        return False
    normalized = instruction.strip().casefold()
    requests_change = any(word in normalized for word in ("remplace", "change", "déplace", "modifie"))
    named_words = re.findall(r"\b[A-ZÀ-ÖØ-Ý][a-zà-öø-ÿ]+\b", instruction)
    has_specific_target = len(named_words) > 1
    return requests_change and not has_specific_target


def _mentions_proximity(instruction: str) -> bool:
    normalized = instruction.strip().casefold()
    return any(word in normalized for word in ("proche", "proximité", "proximite", "distance", "près", "pres"))


class InstructionInterpreter(Protocol):
    def interpret(self, instruction: str | None) -> InstructionDecision: ...


class RegexInstructionInterpreter:
    """Interprète déterministe sans appel modèle, utilisée par défaut et comme filet de sécurité."""

    def interpret(self, instruction: str | None) -> InstructionDecision:
        if _ambiguous(instruction):
            return InstructionDecision(
                needs_clarification=True,
                clarification_question="Quelle personne ou quel poste faut-il modifier ?",
            )
        multiplier = 3.0 if instruction and _mentions_proximity(instruction) else 1.0
        return InstructionDecision(proximity_weight_multiplier=multiplier)


class StrandsInstructionInterpreter:
    """Utilise l'agent Strands pour interpréter l'instruction en une décision structurée bornée."""

    def __init__(self, model=None) -> None:
        self._agent = build_instruction_interpreter(model)

    def interpret(self, instruction: str | None) -> InstructionDecision:
        if not instruction:
            return InstructionDecision()
        result = self._agent(instruction, structured_output_model=InstructionDecision)
        if result.structured_output is None:
            raise RuntimeError("L'agent d'interprétation n'a pas produit de sortie structurée")
        return result.structured_output


class LocalNeighborLinkWorkflow:
    """Chemin reproductible utilisant exactement les mêmes implémentations que les outils Strands."""

    def __init__(self, interpreter: InstructionInterpreter | None = None) -> None:
        self.interpreter = interpreter or RegexInstructionInterpreter()

    def _decide(self, instruction: str | None) -> InstructionDecision:
        try:
            return self.interpreter.interpret(instruction)
        except Exception:
            return RegexInstructionInterpreter().interpret(instruction)

    def run(self, request: AgentRequest) -> AgentResponse:
        decision = self._decide(request.instruction)
        if decision.needs_clarification:
            return AgentResponse(
                status="needs_clarification",
                clarification_question=decision.clarification_question,
            )
        journal: list[ToolCallRecord] = []
        payload = request.operation_snapshot.model_dump(mode="json")
        payload["proximity_weight_multiplier"] = decision.proximity_weight_multiplier
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
