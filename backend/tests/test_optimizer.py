from datetime import UTC, datetime, timedelta

from app.optimizer import (
    AvailabilityInput,
    ScheduleInput,
    ShiftInput,
    VolunteerInput,
    optimize_schedule,
)

START = datetime(2026, 9, 20, 8, tzinfo=UTC)


def volunteer(
    identifier: str,
    *,
    skills: set[str] | None = None,
    start: datetime = START,
    end: datetime = START + timedelta(hours=8),
    preferred_roles: set[str] | None = None,
) -> VolunteerInput:
    return VolunteerInput(
        id=identifier,
        display_name=identifier,
        skills=skills or {"distribution"},
        availability=[AvailabilityInput(starts_at=start, ends_at=end)],
        preferred_roles=preferred_roles or set(),
    )


def shift(
    identifier: str,
    *,
    start: datetime = START,
    end: datetime = START + timedelta(hours=2),
    capacity: int = 1,
    skill: str = "distribution",
) -> ShiftInput:
    return ShiftInput(
        id=identifier,
        name=identifier,
        role_name="Distribution",
        required_skill=skill,
        starts_at=start,
        ends_at=end,
        capacity=capacity,
    )


def test_perfect_schedule_respects_skills_and_capacity() -> None:
    result = optimize_schedule(
        ScheduleInput(volunteers=[volunteer("a"), volunteer("b")], shifts=[shift("s", capacity=2)])
    )
    assert result.status == "complete"
    assert len(result.assignments) == 2
    assert result.uncovered_requirements == []


def test_conflicting_shifts_do_not_double_book_volunteer() -> None:
    result = optimize_schedule(
        ScheduleInput(volunteers=[volunteer("a")], shifts=[shift("s1"), shift("s2")])
    )
    assert result.status == "partial"
    assert len(result.assignments) == 1
    assert len(result.uncovered_requirements) == 1


def test_tie_break_is_deterministic() -> None:
    payload = ScheduleInput(
        volunteers=[volunteer("b"), volunteer("a")],
        shifts=[shift("s")],
    )
    first = optimize_schedule(payload)
    second = optimize_schedule(payload)
    assert first == second
    assert first.assignments[0].volunteer_id == "a"


def test_partial_solution_reports_missing_capacity_and_cause() -> None:
    result = optimize_schedule(
        ScheduleInput(
            volunteers=[volunteer("a", skills={"accueil"})],
            shifts=[shift("s", capacity=2)],
        )
    )
    assert result.status == "partial"
    assert result.uncovered_requirements[0].missing_positions == 2
    assert "compétence" in result.uncovered_requirements[0].cause


def test_preference_breaks_tie_after_hard_constraints() -> None:
    result = optimize_schedule(
        ScheduleInput(
            volunteers=[
                volunteer("a"),
                volunteer("b", preferred_roles={"distribution"}),
            ],
            shifts=[shift("s")],
        )
    )
    assert result.assignments[0].volunteer_id == "b"
    assert "preferred_role" in result.assignments[0].reason_codes


def test_proximity_weight_multiplier_scales_proximity_score_deterministically() -> None:
    close_volunteer = volunteer("a")
    close_volunteer.latitude = 0.0
    close_volunteer.longitude = 0.0
    close_shift = shift("s")
    close_shift.latitude = 0.05
    close_shift.longitude = 0.0

    baseline = optimize_schedule(
        ScheduleInput(volunteers=[close_volunteer], shifts=[close_shift], proximity_weight_multiplier=1.0)
    )
    boosted = optimize_schedule(
        ScheduleInput(volunteers=[close_volunteer], shifts=[close_shift], proximity_weight_multiplier=3.0)
    )
    repeat_boosted = optimize_schedule(
        ScheduleInput(volunteers=[close_volunteer], shifts=[close_shift], proximity_weight_multiplier=3.0)
    )

    assert boosted.score["proximity"] > baseline.score["proximity"]
    assert boosted.score["proximity"] == repeat_boosted.score["proximity"]
    assert boosted.score["proximity"] == round(baseline.score["proximity"] * 3)
