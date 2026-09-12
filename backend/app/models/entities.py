from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Africa/Douala")


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    cognito_sub: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)


class Membership(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "organization_id", name="membership_user_organization"),
        CheckConstraint("role IN ('coordinator', 'viewer')", name="membership_role"),
        Index("ix_memberships_organization_user", "organization_id", "user_id"),
    )

    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    organization_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(24), nullable=False, default="coordinator")

    user: Mapped[User] = relationship()
    organization: Mapped[Organization] = relationship()


class Operation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "operations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'ready', 'active', 'completed', 'cancelled')",
            name="operation_status",
        ),
        Index("ix_operations_organization_date", "organization_id", "event_date"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    location_name: Mapped[str] = mapped_column(String(240), nullable=False)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")


class Shift(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "shifts"
    __table_args__ = (
        CheckConstraint("capacity > 0", name="shift_positive_capacity"),
        CheckConstraint("ends_at > starts_at", name="shift_time_order"),
        Index("ix_shifts_organization_operation", "organization_id", "operation_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    operation_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("operations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    role_name: Mapped[str] = mapped_column(String(120), nullable=False)
    required_skill: Mapped[str | None] = mapped_column(String(120))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)


class Volunteer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "volunteers"
    __table_args__ = (
        UniqueConstraint("organization_id", "email", name="volunteer_organization_email"),
        Index("ix_volunteers_organization_name", "organization_id", "display_name"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    phone_e164: Mapped[str | None] = mapped_column(String(20))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    preferences: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    email_consent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    whatsapp_consent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class VolunteerAvailability(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "volunteer_availabilities"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="availability_time_order"),
        Index("ix_availabilities_organization_volunteer", "organization_id", "volunteer_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    volunteer_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("volunteers.id", ondelete="CASCADE"), nullable=False
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class VolunteerSkill(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "volunteer_skills"
    __table_args__ = (
        UniqueConstraint("volunteer_id", "skill_name", name="volunteer_skill_name"),
        Index("ix_skills_organization_volunteer", "organization_id", "volunteer_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    volunteer_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("volunteers.id", ondelete="CASCADE"), nullable=False
    )
    skill_name: Mapped[str] = mapped_column(String(120), nullable=False)


class ScheduleVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "schedule_versions"
    __table_args__ = (
        UniqueConstraint("operation_id", "revision", name="schedule_operation_revision"),
        CheckConstraint(
            "status IN ('draft', 'approved', 'published', 'superseded')",
            name="schedule_status",
        ),
        Index("ix_schedule_versions_organization_operation", "organization_id", "operation_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    operation_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("operations.id", ondelete="CASCADE"), nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    origin: Mapped[str] = mapped_column(String(32), nullable=False, default="agent")
    total_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    score_details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    conflicts: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    explanations: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    agent_session_id: Mapped[str | None] = mapped_column(String(64))
    agent_request_id: Mapped[str | None] = mapped_column(String(64))
    tool_calls: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    approved_by_user_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Assignment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "assignments"
    __table_args__ = (
        UniqueConstraint("schedule_version_id", "shift_id", "volunteer_id", name="assignment_once"),
        CheckConstraint(
            "response_status IN ('pending', 'confirmed', 'declined')",
            name="assignment_response_status",
        ),
        Index("ix_assignments_organization_version", "organization_id", "schedule_version_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    schedule_version_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("schedule_versions.id", ondelete="CASCADE"), nullable=False
    )
    shift_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("shifts.id", ondelete="CASCADE"), nullable=False
    )
    volunteer_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("volunteers.id", ondelete="CASCADE"), nullable=False
    )
    response_status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    score_details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class NotificationOutbox(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "notification_outbox"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="notification_idempotency_key"),
        CheckConstraint("channel IN ('email', 'whatsapp')", name="notification_channel"),
        CheckConstraint("mode IN ('real', 'simulated')", name="notification_mode"),
        CheckConstraint(
            "status IN ('pending', 'sent', 'simulated', 'failed')",
            name="notification_status",
        ),
        Index("ix_notification_outbox_organization_status", "organization_id", "status"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    schedule_version_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("schedule_versions.id", ondelete="CASCADE"), nullable=False
    )
    assignment_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    recipient: Mapped[str] = mapped_column(String(320), nullable=False)
    rendered_content: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(String(180), nullable=False)


class VolunteerResponse(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "volunteer_responses"
    __table_args__ = (
        UniqueConstraint("token_fingerprint", name="response_token_fingerprint"),
        CheckConstraint("decision IN ('confirm', 'decline')", name="response_decision"),
        Index("ix_volunteer_responses_organization_assignment", "organization_id", "assignment_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    schedule_version_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("schedule_versions.id", ondelete="CASCADE"), nullable=False
    )
    assignment_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False
    )
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    token_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    responded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AuditEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint("actor_type IN ('human', 'agent', 'system')", name="audit_actor_type"),
        Index("ix_audit_events_organization_created", "organization_id", "created_at"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(80), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
