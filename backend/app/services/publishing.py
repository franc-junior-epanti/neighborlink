from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.integrations.notifications import NotificationAdapter, SimulatedAdapter, build_registry
from app.models import (
    Assignment,
    AuditEvent,
    NotificationOutbox,
    ScheduleVersion,
    Shift,
    Volunteer,
)
from app.schemas.publishing import NotificationPreviewItem, OutboxStatusView
from app.services.responses import sign_response_token


class PublishConflict(ValueError):
    """Raised when a schedule version cannot be published as requested."""


def _response_links(assignment_id: UUID) -> tuple[str, str]:
    settings = get_settings()
    base = settings.public_api_base_url.rstrip("/")
    confirm = sign_response_token(settings.response_signing_secret, assignment_id, "confirm")
    decline = sign_response_token(settings.response_signing_secret, assignment_id, "decline")
    return (
        f"{base}/api/v1/public/responses/{confirm}",
        f"{base}/api/v1/public/responses/{decline}",
    )


def _render_message(volunteer: Volunteer, shift: Shift, version: ScheduleVersion, assignment_id: UUID) -> str:
    confirm_url, decline_url = _response_links(assignment_id)
    return (
        f"Bonjour {volunteer.display_name}, vous êtes proposé(e) pour \"{shift.name}\" "
        f"le {shift.starts_at:%d/%m/%Y} de {shift.starts_at:%H:%M} à {shift.ends_at:%H:%M} "
        f"(planning v{version.revision}).\n"
        f"Confirmer : {confirm_url}\n"
        f"Décliner : {decline_url}"
    )


def _choose_channel(volunteer: Volunteer) -> tuple[str, str] | None:
    # WhatsApp channel selection is temporarily disabled (email-only for the hackathon
    # deadline); the WhatsApp adapter/integration code stays in place for later reactivation.
    if volunteer.email_consent and volunteer.email:
        return "email", volunteer.email
    return None


def _assignment_rows(db: Session, version_id: UUID):
    return db.execute(
        select(Assignment, Volunteer, Shift)
        .join(Volunteer, Volunteer.id == Assignment.volunteer_id)
        .join(Shift, Shift.id == Assignment.shift_id)
        .where(Assignment.schedule_version_id == version_id)
        .order_by(Shift.starts_at, Volunteer.display_name)
    ).all()


def preview_notifications(db: Session, version: ScheduleVersion) -> list[NotificationPreviewItem]:
    items = []
    for assignment, volunteer, shift in _assignment_rows(db, version.id):
        picked = _choose_channel(volunteer)
        items.append(
            NotificationPreviewItem(
                assignment_id=assignment.id,
                volunteer_id=volunteer.id,
                volunteer_name=volunteer.display_name,
                channel=picked[0] if picked else None,
                recipient=picked[1] if picked else None,
                content=_render_message(volunteer, shift, version, assignment.id),
                blocked_reason=None if picked else "Aucun canal consenti par le bénévole.",
            )
        )
    return items


def _to_status_view(row: NotificationOutbox) -> OutboxStatusView:
    return OutboxStatusView(
        id=row.id,
        assignment_id=row.assignment_id,
        channel=row.channel,
        recipient=row.recipient,
        mode=row.mode,
        status=row.status,
        attempt_count=row.attempt_count,
        last_error=row.last_error,
    )


def publish_version(
    db: Session,
    version: ScheduleVersion,
    expected_revision: int,
    actor_id: UUID,
    registry: dict[str, NotificationAdapter] | None = None,
) -> tuple[ScheduleVersion, list[OutboxStatusView]]:
    if version.revision != expected_revision:
        raise PublishConflict("Cette version a changé depuis votre dernière lecture ; rechargez.")
    if version.status != "draft":
        raise PublishConflict("Cette version n'est plus un brouillon publiable.")

    registry = registry or build_registry(get_settings())

    db.execute(
        update(ScheduleVersion)
        .where(
            ScheduleVersion.operation_id == version.operation_id,
            ScheduleVersion.status == "published",
        )
        .values(status="superseded")
    )

    version.status = "published"
    version.approved_by_user_id = actor_id
    version.approved_at = datetime.now(UTC)

    created: list[NotificationOutbox] = []
    for assignment, volunteer, shift in _assignment_rows(db, version.id):
        picked = _choose_channel(volunteer)
        if picked is None:
            continue
        channel, recipient = picked
        idempotency_key = f"{version.id}:{assignment.id}:{channel}"
        existing = db.scalar(
            select(NotificationOutbox).where(
                NotificationOutbox.idempotency_key == idempotency_key
            )
        )
        if existing is not None:
            created.append(existing)
            continue
        mode = "simulated" if isinstance(registry.get(channel), SimulatedAdapter) else "real"
        row = NotificationOutbox(
            organization_id=version.organization_id,
            schedule_version_id=version.id,
            assignment_id=assignment.id,
            channel=channel,
            recipient=recipient,
            rendered_content=_render_message(volunteer, shift, version, assignment.id),
            mode=mode,
            status="pending",
            idempotency_key=idempotency_key,
        )
        db.add(row)
        created.append(row)

    db.add(
        AuditEvent(
            organization_id=version.organization_id,
            actor_type="human",
            actor_id=str(actor_id),
            action="schedule_version.published",
            resource_type="schedule_version",
            resource_id=str(version.id),
            event_metadata={"revision": version.revision, "notifications": len(created)},
        )
    )
    db.commit()
    db.refresh(version)
    return version, [_to_status_view(row) for row in created]


def dispatch_pending(
    db: Session, version_id: UUID, registry: dict[str, NotificationAdapter] | None = None
) -> list[OutboxStatusView]:
    registry = registry or build_registry(get_settings())
    rows = list(
        db.scalars(
            select(NotificationOutbox).where(
                NotificationOutbox.schedule_version_id == version_id,
                NotificationOutbox.status == "pending",
            )
        )
    )
    for row in rows:
        adapter = registry.get(row.channel, SimulatedAdapter())
        row.attempt_count += 1
        try:
            ok = adapter.send(row)
        except Exception as exc:  # noqa: BLE001 - any adapter failure is a delivery failure
            ok = False
            row.last_error = str(exc)
        if ok:
            row.status = "simulated" if row.mode == "simulated" else "sent"
            row.last_error = None
        else:
            row.status = "failed"
            row.last_error = row.last_error or "Échec d'envoi"
    if rows:
        db.add(
            AuditEvent(
                organization_id=rows[0].organization_id,
                actor_type="system",
                actor_id="notification-worker",
                action="notification_outbox.dispatched",
                resource_type="schedule_version",
                resource_id=str(version_id),
                event_metadata={"processed": len(rows)},
            )
        )
    db.commit()
    return [_to_status_view(row) for row in rows]


def list_notifications(db: Session, version_id: UUID) -> list[OutboxStatusView]:
    rows = db.scalars(
        select(NotificationOutbox)
        .where(NotificationOutbox.schedule_version_id == version_id)
        .order_by(NotificationOutbox.created_at)
    )
    return [_to_status_view(row) for row in rows]
