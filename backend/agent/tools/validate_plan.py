from collections import Counter, defaultdict
from itertools import pairwise

from strands import tool

from app.optimizer import ScheduleInput, ScheduleResult


def run_validation(payload: dict, proposed_schedule: dict) -> dict:
    data = ScheduleInput.model_validate(payload)
    result = ScheduleResult.model_validate(proposed_schedule)
    volunteers = {item.id: item for item in data.volunteers}
    shifts = {item.id: item for item in data.shifts}
    violations: list[str] = []
    seen_pairs = set()
    by_volunteer = defaultdict(list)
    capacity = Counter()

    for assignment in result.assignments:
        pair = (assignment.volunteer_id, assignment.shift_id)
        if pair in seen_pairs:
            violations.append(f"duplicate_assignment:{assignment.volunteer_id}:{assignment.shift_id}")
            continue
        seen_pairs.add(pair)
        volunteer = volunteers.get(assignment.volunteer_id)
        shift = shifts.get(assignment.shift_id)
        if volunteer is None or shift is None:
            violations.append(f"unknown_reference:{assignment.volunteer_id}:{assignment.shift_id}")
            continue
        if shift.required_skill and shift.required_skill.casefold() not in {
            skill.casefold() for skill in volunteer.skills
        }:
            violations.append(f"missing_skill:{volunteer.id}:{shift.id}")
        if not any(
            window.starts_at <= shift.starts_at and window.ends_at >= shift.ends_at
            for window in volunteer.availability
        ):
            violations.append(f"unavailable:{volunteer.id}:{shift.id}")
        capacity[shift.id] += 1
        by_volunteer[volunteer.id].append(shift)

    for shift_id, count in capacity.items():
        if count > shifts[shift_id].capacity:
            violations.append(f"capacity_exceeded:{shift_id}")
    for volunteer_id, assigned_shifts in by_volunteer.items():
        ordered = sorted(assigned_shifts, key=lambda item: item.starts_at)
        for left, right in pairwise(ordered):
            if left.ends_at > right.starts_at:
                violations.append(f"overlap:{volunteer_id}:{left.id}:{right.id}")
    return {"valid": not violations, "violations": violations}


@tool
def validate_plan(payload: dict, proposed_schedule: dict) -> dict:
    """Revérifie indépendamment toutes les contraintes dures d'un planning proposé."""
    return run_validation(payload, proposed_schedule)
