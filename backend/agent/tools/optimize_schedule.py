from strands import tool

from app.optimizer import ScheduleInput
from app.optimizer import optimize_schedule as solve


def run_optimizer(payload: dict) -> dict:
    schedule_input = ScheduleInput.model_validate(payload)
    return solve(schedule_input).model_dump(mode="json")


@tool
def optimize_schedule(payload: dict) -> dict:
    """Calcule un planning avec CP-SAT à partir d'un ScheduleInput strict et retourne le résultat structuré."""
    return run_optimizer(payload)
