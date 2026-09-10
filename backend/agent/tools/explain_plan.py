from strands import tool

from app.optimizer import ScheduleInput, ScheduleResult


def run_explanation(payload: dict, proposed_schedule: dict) -> dict:
    data = ScheduleInput.model_validate(payload)
    result = ScheduleResult.model_validate(proposed_schedule)
    volunteers = {item.id: item for item in data.volunteers}
    shifts = {item.id: item for item in data.shifts}
    facts = []
    for assignment in result.assignments:
        volunteer = volunteers[assignment.volunteer_id]
        shift = shifts[assignment.shift_id]
        reasons = ", ".join(assignment.reason_codes)
        distance = (
            f", distance {assignment.distance_km:.1f} km"
            if assignment.distance_km is not None
            else ""
        )
        facts.append(
            f"{volunteer.display_name} → {shift.name}: {reasons}{distance}."
        )
    for missing in result.uncovered_requirements:
        facts.append(
            f"{missing.shift_name}: {missing.missing_positions} poste(s) non couvert(s), "
            f"cause: {missing.cause}."
        )
    return {"facts": facts, "score": result.score}


@tool
def explain_plan(payload: dict, proposed_schedule: dict) -> dict:
    """Produit uniquement des faits explicables issus du planning calculé, sans modifier les scores."""
    return run_explanation(payload, proposed_schedule)
