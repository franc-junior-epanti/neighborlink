from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.api.session import CurrentIdentity, DatabaseSession
from app.models import ScheduleVersion
from app.repositories.session import get_membership, synchronize_user
from app.schemas.publishing import (
    DispatchResult,
    NotificationPreviewItem,
    OutboxStatusView,
    PublishRequest,
    PublishResult,
)
from app.services.publishing import (
    PublishConflict,
    dispatch_pending,
    list_notifications,
    preview_notifications,
    publish_version,
)

router = APIRouter(prefix="/api/v1", tags=["publishing"])


def _authorized_version(
    version_id: UUID, identity: CurrentIdentity, db: DatabaseSession
) -> tuple[object, ScheduleVersion]:
    user = synchronize_user(db, identity)
    version = db.get(ScheduleVersion, version_id)
    if version is None or get_membership(db, user.id, version.organization_id) is None:
        raise HTTPException(status_code=404, detail="Version introuvable")
    return user, version


@router.get(
    "/schedule-versions/{version_id}/notifications/preview",
    response_model=list[NotificationPreviewItem],
)
def preview(
    version_id: UUID, identity: CurrentIdentity, db: DatabaseSession
) -> list[NotificationPreviewItem]:
    _, version = _authorized_version(version_id, identity, db)
    return preview_notifications(db, version)


@router.post(
    "/schedule-versions/{version_id}/publish",
    response_model=PublishResult,
    status_code=status.HTTP_200_OK,
)
def publish(
    version_id: UUID,
    payload: PublishRequest,
    identity: CurrentIdentity,
    db: DatabaseSession,
) -> PublishResult:
    user, version = _authorized_version(version_id, identity, db)
    try:
        published, notifications = publish_version(
            db, version, payload.expected_revision, user.id
        )
    except PublishConflict as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return PublishResult(
        schedule_version_id=published.id,
        status=published.status,
        approved_at=published.approved_at,
        notifications=notifications,
    )


@router.post(
    "/schedule-versions/{version_id}/notifications/dispatch",
    response_model=DispatchResult,
)
def dispatch(
    version_id: UUID, identity: CurrentIdentity, db: DatabaseSession
) -> DispatchResult:
    _, version = _authorized_version(version_id, identity, db)
    if version.status != "published":
        raise HTTPException(
            status_code=409, detail="Seule une version publiée peut être notifiée."
        )
    return DispatchResult(notifications=dispatch_pending(db, version.id))


@router.get(
    "/schedule-versions/{version_id}/notifications",
    response_model=list[OutboxStatusView],
)
def read_outbox_status(
    version_id: UUID, identity: CurrentIdentity, db: DatabaseSession
) -> list[OutboxStatusView]:
    _, version = _authorized_version(version_id, identity, db)
    return list_notifications(db, version.id)
