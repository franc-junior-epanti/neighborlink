import base64
import hashlib
import hmac
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Assignment, AuditEvent, VolunteerResponse


class InvalidResponseToken(ValueError):
    """Raised when a confirm/decline link is malformed or has been tampered with."""


def _signature(secret: str, assignment_id: UUID, decision: str) -> str:
    payload = f"{assignment_id}.{decision}".encode()
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()[:32]


def sign_response_token(secret: str, assignment_id: UUID, decision: str) -> str:
    signature = _signature(secret, assignment_id, decision)
    raw = f"{assignment_id}.{decision}.{signature}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_token(secret: str, token: str) -> tuple[UUID, str]:
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        assignment_id_raw, decision, signature = raw.rsplit(".", 2)
        assignment_id = UUID(assignment_id_raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise InvalidResponseToken("Lien invalide.") from exc
    if decision not in {"confirm", "decline"}:
        raise InvalidResponseToken("Lien invalide.")
    expected = _signature(secret, assignment_id, decision)
    if not hmac.compare_digest(expected, signature):
        raise InvalidResponseToken("Lien invalide ou altéré.")
    return assignment_id, decision


def record_response(db: Session, secret: str, token: str) -> VolunteerResponse:
    assignment_id, decision = _decode_token(secret, token)
    fingerprint = hashlib.sha256(token.encode()).hexdigest()

    existing = db.scalar(
        select(VolunteerResponse).where(VolunteerResponse.token_fingerprint == fingerprint)
    )
    if existing is not None:
        return existing

    assignment = db.get(Assignment, assignment_id)
    if assignment is None:
        raise InvalidResponseToken("Affectation introuvable.")

    response = VolunteerResponse(
        organization_id=assignment.organization_id,
        schedule_version_id=assignment.schedule_version_id,
        assignment_id=assignment.id,
        decision=decision,
        token_fingerprint=fingerprint,
        responded_at=datetime.now(UTC),
    )
    assignment.response_status = "confirmed" if decision == "confirm" else "declined"
    db.add(response)
    db.add(
        AuditEvent(
            organization_id=assignment.organization_id,
            actor_type="human",
            actor_id=None,
            action="volunteer_response.recorded",
            resource_type="assignment",
            resource_id=str(assignment.id),
            event_metadata={"decision": decision},
        )
    )
    db.commit()
    db.refresh(response)
    return response
