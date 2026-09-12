from collections import defaultdict
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agent.contracts import AgentRequest
from app.integrations.agent_runtime import AgentRuntime
from app.models import (
    Assignment,
    AuditEvent,
    Operation,
    ScheduleVersion,
    Shift,
    Volunteer,
    VolunteerAvailability,
    VolunteerSkill,
)
from app.optimizer import AvailabilityInput, ScheduleInput, ShiftInput, VolunteerInput
from app.schemas.schedules import (
    AssignmentView,
    ScheduleDiff,
    ScheduleVersionDetail,
    ScheduleVersionSummary,
    ShiftView,
    ToolCallView,
)


def list_operations(db: Session, organization_id: UUID) -> list[Operation]:
    return list(
        db.scalars(
            select(Operation)
            .where(Operation.organization_id == organization_id)
            .order_by(Operation.event_date.desc())
        )
    )


def get_operation(db: Session, operation_id: UUID, organization_id: UUID) -> Operation | None:
    return db.scalar(
        select(Operation).where(
            Operation.id == operation_id,
            Operation.organization_id == organization_id,
        )
    )


def _snapshot(db: Session, operation: Operation) -> ScheduleInput:
    shifts = list(
        db.scalars(select(Shift).where(Shift.operation_id == operation.id).order_by(Shift.starts_at))
    )
    volunteers = list(
        db.scalars(
            select(Volunteer)
            .where(Volunteer.organization_id == operation.organization_id)
            .order_by(Volunteer.display_name)
        )
    )
    skills: dict[UUID, set[str]] = defaultdict(set)
    for row in db.scalars(
        select(VolunteerSkill).where(VolunteerSkill.organization_id == operation.organization_id)
    ):
        skills[row.volunteer_id].add(row.skill_name)
    availability: dict[UUID, list[AvailabilityInput]] = defaultdict(list)
    for row in db.scalars(
        select(VolunteerAvailability).where(
            VolunteerAvailability.organization_id == operation.organization_id
        )
    ):
        availability[row.volunteer_id].append(
            AvailabilityInput(starts_at=row.starts_at, ends_at=row.ends_at)
        )
    return ScheduleInput(
        volunteers=[
            VolunteerInput(
                id=str(volunteer.id),
                display_name=volunteer.display_name,
                skills=skills[volunteer.id],
                availability=availability[volunteer.id],
                preferred_roles=set(volunteer.preferences.get("preferred_roles", [])),
                latitude=float(volunteer.latitude) if volunteer.latitude is not None else None,
                longitude=float(volunteer.longitude) if volunteer.longitude is not None else None,
            )
            for volunteer in volunteers
        ],
        shifts=[
            ShiftInput(
                id=str(shift.id),
                name=shift.name,
                role_name=shift.role_name,
                required_skill=shift.required_skill,
                starts_at=shift.starts_at,
                ends_at=shift.ends_at,
                capacity=shift.capacity,
                latitude=float(operation.latitude) if operation.latitude is not None else None,
                longitude=float(operation.longitude) if operation.longitude is not None else None,
            )
            for shift in shifts
        ],
    )


def _next_revision(db: Session, operation_id: UUID) -> int:
    current = db.scalar(
        select(func.max(ScheduleVersion.revision)).where(
            ScheduleVersion.operation_id == operation_id
        )
    )
    return int(current or 0) + 1


def create_schedule_version(
    db: Session,
    operation: Operation,
    runtime: AgentRuntime,
    instruction: str | None,
    actor_id: str,
) -> ScheduleVersion:
    request = AgentRequest(
        session_id=str(operation.id),
        organization_id=str(operation.organization_id),
        operation_snapshot=_snapshot(db, operation),
        instruction=instruction,
    )
    response = runtime.invoke(request)
    if response.schedule is None:
        raise ValueError(response.clarification_question or "Aucun planning proposé")
    schedule = response.schedule
    version = ScheduleVersion(
        organization_id=operation.organization_id,
        operation_id=operation.id,
        revision=_next_revision(db, operation.id),
        status="draft",
        origin="agent",
        total_score=schedule.score.get("total", 0),
        score_details=schedule.score,
        conflicts=[
            f"{item.shift_name}: {item.missing_positions} poste(s) — {item.cause}"
            for item in schedule.uncovered_requirements
        ],
        explanations=response.explanations,
        agent_session_id=request.session_id,
        agent_request_id=request.request_id,
        tool_calls=[call.model_dump(mode="json") for call in response.tool_calls],
    )
    db.add(version)
    db.flush()
    for item in schedule.assignments:
        db.add(
            Assignment(
                organization_id=operation.organization_id,
                schedule_version_id=version.id,
                shift_id=UUID(item.shift_id),
                volunteer_id=UUID(item.volunteer_id),
                score_details={
                    "reason_codes": item.reason_codes,
                    "distance_km": item.distance_km,
                },
            )
        )
    db.add(
        AuditEvent(
            organization_id=operation.organization_id,
            actor_type="human",
            actor_id=actor_id,
            action="schedule_version.created",
            resource_type="schedule_version",
            resource_id=str(version.id),
            event_metadata={"revision": version.revision, "origin": version.origin},
        )
    )
    db.commit()
    db.refresh(version)
    return version


def list_versions(db: Session, operation_id: UUID) -> list[ScheduleVersionSummary]:
    versions = db.scalars(
        select(ScheduleVersion)
        .where(ScheduleVersion.operation_id == operation_id)
        .order_by(ScheduleVersion.revision.desc())
    )
    return [
        ScheduleVersionSummary(
            id=item.id,
            revision=item.revision,
            status=item.status,
            origin=item.origin,
            total_score=item.total_score,
            created_at=item.created_at,
        )
        for item in versions
    ]


def get_version(db: Session, version_id: UUID, organization_id: UUID) -> ScheduleVersion | None:
    return db.scalar(
        select(ScheduleVersion).where(
            ScheduleVersion.id == version_id,
            ScheduleVersion.organization_id == organization_id,
        )
    )


def version_detail(db: Session, version: ScheduleVersion) -> ScheduleVersionDetail:
    rows = db.execute(
        select(Assignment, Volunteer, Shift)
        .join(Volunteer, Volunteer.id == Assignment.volunteer_id)
        .join(Shift, Shift.id == Assignment.shift_id)
        .where(Assignment.schedule_version_id == version.id)
        .order_by(Shift.starts_at, Volunteer.display_name)
    ).all()
    shifts = list(
        db.scalars(
            select(Shift)
            .where(Shift.operation_id == version.operation_id)
            .order_by(Shift.starts_at)
        )
    )
    return ScheduleVersionDetail(
        id=version.id,
        operation_id=version.operation_id,
        revision=version.revision,
        status=version.status,
        origin=version.origin,
        total_score=version.total_score,
        score_details=version.score_details,
        conflicts=version.conflicts,
        explanations=version.explanations,
        created_at=version.created_at,
        agent_session_id=version.agent_session_id,
        agent_request_id=version.agent_request_id,
        tool_calls=[ToolCallView(**call) for call in version.tool_calls],
        approved_at=version.approved_at,
        assignments=[
            AssignmentView(
                id=assignment.id,
                volunteer_id=volunteer.id,
                volunteer_name=volunteer.display_name,
                shift_id=shift.id,
                shift_name=shift.name,
                starts_at=shift.starts_at,
                ends_at=shift.ends_at,
                response_status=assignment.response_status,
                reason_codes=assignment.score_details.get("reason_codes", []),
                distance_km=assignment.score_details.get("distance_km"),
            )
            for assignment, volunteer, shift in rows
        ],
        shifts=[
            ShiftView(
                id=shift.id,
                name=shift.name,
                role_name=shift.role_name,
                starts_at=shift.starts_at,
                ends_at=shift.ends_at,
                capacity=shift.capacity,
            )
            for shift in shifts
        ],
    )


def _move_conflict(
    db: Session,
    base: ScheduleVersion,
    volunteer: Volunteer,
    target: Shift,
    from_shift_id: UUID | None,
) -> str | None:
    has_skill = target.required_skill is None or db.scalar(
        select(VolunteerSkill.id).where(
            VolunteerSkill.volunteer_id == volunteer.id,
            VolunteerSkill.skill_name == target.required_skill,
        )
    )
    if not has_skill:
        return f"{volunteer.display_name} ne possède pas la compétence {target.required_skill}."
    available = db.scalar(
        select(VolunteerAvailability.id).where(
            VolunteerAvailability.volunteer_id == volunteer.id,
            VolunteerAvailability.starts_at <= target.starts_at,
            VolunteerAvailability.ends_at >= target.ends_at,
        )
    )
    if not available:
        return f"{volunteer.display_name} n’est pas disponible sur ce créneau."
    assignments = db.execute(
        select(Assignment, Shift)
        .join(Shift, Shift.id == Assignment.shift_id)
        .where(Assignment.schedule_version_id == base.id)
    ).all()
    target_count = sum(
        1
        for assignment, _shift in assignments
        if assignment.shift_id == target.id
        and not (assignment.volunteer_id == volunteer.id and assignment.shift_id == from_shift_id)
    )
    if target_count >= target.capacity:
        return f"Le créneau {target.name} a déjà atteint sa capacité."
    for assignment, shift in assignments:
        if assignment.volunteer_id != volunteer.id or assignment.shift_id == from_shift_id:
            continue
        if shift.starts_at < target.ends_at and target.starts_at < shift.ends_at:
            return f"{volunteer.display_name} est déjà affecté sur un créneau qui se chevauche."
    return None


def move_assignment(
    db: Session,
    base: ScheduleVersion,
    volunteer_id: UUID,
    target_shift_id: UUID,
    from_shift_id: UUID | None,
    actor_id: str,
) -> ScheduleVersion:
    if base.status == "published":
        # Une version publiée reste immuable ; la modification est portée par une copie brouillon.
        pass
    volunteer = db.scalar(
        select(Volunteer).where(
            Volunteer.id == volunteer_id,
            Volunteer.organization_id == base.organization_id,
        )
    )
    target = db.scalar(
        select(Shift).where(
            Shift.id == target_shift_id,
            Shift.operation_id == base.operation_id,
        )
    )
    if volunteer is None or target is None:
        raise ValueError("Bénévole ou créneau introuvable")
    conflict = _move_conflict(db, base, volunteer, target, from_shift_id)
    if conflict:
        raise ValueError(conflict)
    version = ScheduleVersion(
        organization_id=base.organization_id,
        operation_id=base.operation_id,
        revision=_next_revision(db, base.operation_id),
        status="draft",
        origin="manual",
        total_score=base.total_score,
        score_details=base.score_details,
        conflicts=[],
        explanations=[*base.explanations, f"Déplacement manuel : {volunteer.display_name} → {target.name}."],
    )
    db.add(version)
    db.flush()
    original = list(
        db.scalars(select(Assignment).where(Assignment.schedule_version_id == base.id))
    )
    moved = False
    for assignment in original:
        if assignment.volunteer_id == volunteer_id and (
            from_shift_id is None or assignment.shift_id == from_shift_id
        ):
            if not moved:
                db.add(
                    Assignment(
                        organization_id=base.organization_id,
                        schedule_version_id=version.id,
                        shift_id=target.id,
                        volunteer_id=volunteer_id,
                        score_details={"reason_codes": ["manual_move"], "distance_km": None},
                    )
                )
                moved = True
            continue
        db.add(
            Assignment(
                organization_id=base.organization_id,
                schedule_version_id=version.id,
                shift_id=assignment.shift_id,
                volunteer_id=assignment.volunteer_id,
                response_status=assignment.response_status,
                score_details=assignment.score_details,
            )
        )
    if not moved:
        db.add(
            Assignment(
                organization_id=base.organization_id,
                schedule_version_id=version.id,
                shift_id=target.id,
                volunteer_id=volunteer_id,
                score_details={"reason_codes": ["manual_move"], "distance_km": None},
            )
        )
    db.add(
        AuditEvent(
            organization_id=base.organization_id,
            actor_type="human",
            actor_id=actor_id,
            action="schedule_version.manual_move",
            resource_type="schedule_version",
            resource_id=str(version.id),
            event_metadata={"base_version_id": str(base.id), "revision": version.revision},
        )
    )
    db.commit()
    db.refresh(version)
    return version


def version_diff(
    db: Session, target: ScheduleVersion, base: ScheduleVersion | None
) -> ScheduleDiff:
    def labels(version: ScheduleVersion | None) -> set[str]:
        if version is None:
            return set()
        rows = db.execute(
            select(Volunteer.display_name, Shift.name)
            .select_from(Assignment)
            .join(Volunteer, Volunteer.id == Assignment.volunteer_id)
            .join(Shift, Shift.id == Assignment.shift_id)
            .where(Assignment.schedule_version_id == version.id)
        ).all()
        return {f"{volunteer} → {shift}" for volunteer, shift in rows}

    target_labels = labels(target)
    base_labels = labels(base)
    return ScheduleDiff(
        base_version_id=base.id if base else None,
        target_version_id=target.id,
        added=sorted(target_labels - base_labels),
        removed=sorted(base_labels - target_labels),
    )
