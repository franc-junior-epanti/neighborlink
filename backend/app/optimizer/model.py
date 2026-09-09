from itertools import combinations

from ortools.sat.python import cp_model

from app.optimizer.schemas import (
    AssignmentResult,
    ScheduleInput,
    ScheduleResult,
    UncoveredRequirement,
)
from app.optimizer.scoring import haversine_km, proximity_points

COVERAGE_WEIGHT = 10_000
PREFERENCE_WEIGHT = 100
FAIRNESS_WEIGHT = 25


def _normalized(value: str) -> str:
    return value.strip().casefold()


def _is_available(volunteer, shift) -> bool:
    return any(
        window.starts_at <= shift.starts_at and window.ends_at >= shift.ends_at
        for window in volunteer.availability
    )


def _has_skill(volunteer, shift) -> bool:
    if not shift.required_skill:
        return True
    return _normalized(shift.required_skill) in {_normalized(skill) for skill in volunteer.skills}


def _overlap(left, right) -> bool:
    return left.starts_at < right.ends_at and right.starts_at < left.ends_at


def _distance(volunteer, shift) -> float | None:
    if None in (volunteer.latitude, volunteer.longitude, shift.latitude, shift.longitude):
        return None
    return haversine_km(
        volunteer.latitude,
        volunteer.longitude,
        shift.latitude,
        shift.longitude,
    )


def optimize_schedule(payload: ScheduleInput) -> ScheduleResult:
    volunteers = sorted(payload.volunteers, key=lambda item: item.id)
    shifts = sorted(payload.shifts, key=lambda item: item.id)
    model = cp_model.CpModel()
    assignments: dict[tuple[int, int], cp_model.IntVar] = {}
    objective_terms = []

    for volunteer_index, volunteer in enumerate(volunteers):
        for shift_index, shift in enumerate(shifts):
            variable = model.new_bool_var(f"assign_{volunteer_index}_{shift_index}")
            assignments[volunteer_index, shift_index] = variable
            if not _is_available(volunteer, shift) or not _has_skill(volunteer, shift):
                model.add(variable == 0)
                continue
            preferred = _normalized(shift.role_name) in {
                _normalized(role) for role in volunteer.preferred_roles
            }
            proximity = proximity_points(_distance(volunteer, shift))
            tie_break = len(volunteers) - volunteer_index
            objective_terms.append(
                variable
                * (COVERAGE_WEIGHT + (PREFERENCE_WEIGHT if preferred else 0) + proximity + tie_break)
            )

    for shift_index, shift in enumerate(shifts):
        model.add(
            sum(assignments[volunteer_index, shift_index] for volunteer_index in range(len(volunteers)))
            <= shift.capacity
        )

    loads = []
    for volunteer_index in range(len(volunteers)):
        load = model.new_int_var(0, len(shifts), f"load_{volunteer_index}")
        model.add(load == sum(assignments[volunteer_index, s] for s in range(len(shifts))))
        loads.append(load)
        for left, right in combinations(range(len(shifts)), 2):
            if _overlap(shifts[left], shifts[right]):
                model.add(
                    assignments[volunteer_index, left] + assignments[volunteer_index, right] <= 1
                )

    if loads:
        max_load = model.new_int_var(0, len(shifts), "max_load")
        min_load = model.new_int_var(0, len(shifts), "min_load")
        model.add_max_equality(max_load, loads)
        model.add_min_equality(min_load, loads)
        objective_terms.append(-(max_load - min_load) * FAIRNESS_WEIGHT)

    model.maximize(sum(objective_terms))
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 0
    status = solver.solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return ScheduleResult(
            status="infeasible",
            assignments=[],
            uncovered_requirements=[
                UncoveredRequirement(
                    shift_id=shift.id,
                    shift_name=shift.name,
                    missing_positions=shift.capacity,
                    cause="Aucune solution calculable",
                )
                for shift in shifts
            ],
            score={"total": 0, "coverage": 0, "preferences": 0, "fairness": 0, "proximity": 0},
        )

    results: list[AssignmentResult] = []
    preference_score = proximity_score = 0
    coverage_by_shift = {shift.id: 0 for shift in shifts}
    solved_loads = []
    for volunteer_index, volunteer in enumerate(volunteers):
        volunteer_load = 0
        for shift_index, shift in enumerate(shifts):
            if not solver.boolean_value(assignments[volunteer_index, shift_index]):
                continue
            volunteer_load += 1
            coverage_by_shift[shift.id] += 1
            distance = _distance(volunteer, shift)
            reasons = ["available", "skill_match"]
            if _normalized(shift.role_name) in {
                _normalized(role) for role in volunteer.preferred_roles
            }:
                reasons.append("preferred_role")
                preference_score += PREFERENCE_WEIGHT
            if distance is not None:
                reasons.append("proximity")
                proximity_score += proximity_points(distance)
            results.append(
                AssignmentResult(
                    volunteer_id=volunteer.id,
                    shift_id=shift.id,
                    reason_codes=reasons,
                    distance_km=round(distance, 2) if distance is not None else None,
                )
            )
        solved_loads.append(volunteer_load)

    uncovered = [
        UncoveredRequirement(
            shift_id=shift.id,
            shift_name=shift.name,
            missing_positions=shift.capacity - coverage_by_shift[shift.id],
            cause="Pas assez de bénévoles disponibles avec la compétence requise",
        )
        for shift in shifts
        if coverage_by_shift[shift.id] < shift.capacity
    ]
    coverage_score = len(results) * COVERAGE_WEIGHT
    fairness_score = -(
        (max(solved_loads) - min(solved_loads)) * FAIRNESS_WEIGHT if solved_loads else 0
    )
    score = {
        "coverage": coverage_score,
        "preferences": preference_score,
        "fairness": fairness_score,
        "proximity": proximity_score,
    }
    score["total"] = sum(score.values())
    return ScheduleResult(
        status="complete" if not uncovered else "partial",
        assignments=sorted(results, key=lambda item: (item.shift_id, item.volunteer_id)),
        uncovered_requirements=uncovered,
        score=score,
    )
