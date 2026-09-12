from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.session import CurrentIdentity, DatabaseSession
from app.integrations.agent_runtime import configured_runtime
from app.models import Membership, Operation, ScheduleVersion
from app.repositories.session import get_membership, synchronize_user
from app.schemas.schedules import (
    GenerateScheduleRequest,
    ManualMoveRequest,
    OperationSummary,
    ScheduleDiff,
    ScheduleVersionDetail,
    ScheduleVersionSummary,
)
from app.services.schedules import (
    create_schedule_version,
    get_version,
    list_operations,
    list_versions,
    move_assignment,
    version_detail,
    version_diff,
)

router = APIRouter(prefix="/api/v1", tags=["schedules"])


def _authorized_organization(
    db: DatabaseSession, identity: CurrentIdentity, organization_id: UUID
):
    user = synchronize_user(db, identity)
    if get_membership(db, user.id, organization_id) is None:
        raise HTTPException(status_code=403, detail="Association interdite")
    return user


@router.get(
    "/organizations/{organization_id}/operations", response_model=list[OperationSummary]
)
def read_operations(
    organization_id: UUID, identity: CurrentIdentity, db: DatabaseSession
) -> list[OperationSummary]:
    _authorized_organization(db, identity, organization_id)
    return [
        OperationSummary(
            id=item.id,
            name=item.name,
            event_date=item.event_date,
            location_name=item.location_name,
            status=item.status,
        )
        for item in list_operations(db, organization_id)
    ]


def _authorized_operation(operation_id: UUID, identity: CurrentIdentity, db: DatabaseSession):
    user = synchronize_user(db, identity)
    operation = db.scalar(
        select(Operation)
        .join(Membership, Membership.organization_id == Operation.organization_id)
        .where(Operation.id == operation_id, Membership.user_id == user.id)
    )
    if operation is not None:
        return user, operation
    raise HTTPException(status_code=404, detail="Opération introuvable")


@router.post(
    "/operations/{operation_id}/schedule-versions",
    response_model=ScheduleVersionDetail,
    status_code=status.HTTP_201_CREATED,
)
def generate_version(
    operation_id: UUID,
    payload: GenerateScheduleRequest,
    identity: CurrentIdentity,
    db: DatabaseSession,
) -> ScheduleVersionDetail:
    user, operation = _authorized_operation(operation_id, identity, db)
    try:
        version = create_schedule_version(
            db, operation, configured_runtime(), payload.instruction, str(user.id)
        )
    except (RuntimeError, ValueError) as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return version_detail(db, version)


@router.get(
    "/operations/{operation_id}/schedule-versions",
    response_model=list[ScheduleVersionSummary],
)
def read_versions(
    operation_id: UUID, identity: CurrentIdentity, db: DatabaseSession
) -> list[ScheduleVersionSummary]:
    _, operation = _authorized_operation(operation_id, identity, db)
    return list_versions(db, operation.id)


@router.get(
    "/operations/{operation_id}/schedule-versions/{version_id}",
    response_model=ScheduleVersionDetail,
)
def read_version(
    operation_id: UUID,
    version_id: UUID,
    identity: CurrentIdentity,
    db: DatabaseSession,
) -> ScheduleVersionDetail:
    _, operation = _authorized_operation(operation_id, identity, db)
    version = get_version(db, version_id, operation.organization_id)
    if version is None or version.operation_id != operation.id:
        raise HTTPException(status_code=404, detail="Version introuvable")
    return version_detail(db, version)


@router.post(
    "/schedule-versions/{version_id}/manual-moves",
    response_model=ScheduleVersionDetail,
    status_code=status.HTTP_201_CREATED,
)
def manual_move(
    version_id: UUID,
    payload: ManualMoveRequest,
    identity: CurrentIdentity,
    db: DatabaseSession,
) -> ScheduleVersionDetail:
    user = synchronize_user(db, identity)
    version = db.get(ScheduleVersion, version_id)
    if version is None or get_membership(db, user.id, version.organization_id) is None:
        raise HTTPException(status_code=404, detail="Version introuvable")
    try:
        moved = move_assignment(
            db,
            version,
            payload.volunteer_id,
            payload.to_shift_id,
            payload.from_shift_id,
            str(user.id),
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return version_detail(db, moved)


@router.get("/schedule-versions/{version_id}/diff", response_model=ScheduleDiff)
def read_diff(
    version_id: UUID,
    identity: CurrentIdentity,
    db: DatabaseSession,
    against: Annotated[UUID | None, Query()] = None,
) -> ScheduleDiff:
    user = synchronize_user(db, identity)
    target = db.get(ScheduleVersion, version_id)
    if target is None or get_membership(db, user.id, target.organization_id) is None:
        raise HTTPException(status_code=404, detail="Version introuvable")
    base = db.get(ScheduleVersion, against) if against else db.scalar(
        select(ScheduleVersion).where(
            ScheduleVersion.operation_id == target.operation_id,
            ScheduleVersion.revision == target.revision - 1,
        )
    )
    if base is not None and base.operation_id != target.operation_id:
        raise HTTPException(status_code=422, detail="Versions incompatibles")
    return version_diff(db, target, base)
