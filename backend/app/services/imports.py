import csv
import io
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import Operation, Shift, Volunteer, VolunteerAvailability, VolunteerSkill
from app.schemas.imports import ImportIssue, ImportPreview, ImportRow

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
REQUIRED_COLUMNS = {"display_name", "email", "skills"}


@dataclass
class StoredPreview:
    organization_id: UUID
    rows: list[ImportRow]
    errors: list[ImportIssue]
    warnings: list[ImportIssue]


_previews: dict[UUID, StoredPreview] = {}


def _as_bool(value: str, default: bool) -> bool:
    if not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "oui"}


def _validate(rows: list[ImportRow]) -> tuple[list[ImportIssue], list[ImportIssue]]:
    errors: list[ImportIssue] = []
    warnings: list[ImportIssue] = []
    seen: dict[str, int] = {}
    for row in rows:
        if not row.display_name.strip():
            errors.append(ImportIssue(row=row.row, field="display_name", message="Nom requis"))
        normalized_email = row.email.strip().lower()
        if not EMAIL_PATTERN.match(normalized_email):
            errors.append(ImportIssue(row=row.row, field="email", message="Courriel invalide"))
        elif normalized_email in seen:
            errors.append(
                ImportIssue(
                    row=row.row,
                    field="email",
                    message=f"Doublon de la ligne {seen[normalized_email]}",
                )
            )
        else:
            seen[normalized_email] = row.row
        if not row.skills:
            warnings.append(ImportIssue(row=row.row, field="skills", message="Aucune compétence"))
    return errors, warnings


def parse_preview(organization_id: UUID, content: bytes) -> ImportPreview:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Le fichier doit être encodé en UTF-8") from exc
    if not text.strip():
        raise ValueError("Le fichier CSV est vide")
    reader = csv.DictReader(io.StringIO(text))
    missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
    if missing:
        raise ValueError(f"Colonnes requises manquantes : {', '.join(sorted(missing))}")
    rows = [
        ImportRow(
            row=index,
            display_name=(raw.get("display_name") or "").strip(),
            email=(raw.get("email") or "").strip().lower(),
            phone_e164=(raw.get("phone_e164") or "").strip(),
            skills=[item.strip() for item in (raw.get("skills") or "").split("|") if item.strip()],
            available=_as_bool(raw.get("available") or "", True),
            email_consent=_as_bool(raw.get("email_consent") or "", True),
            whatsapp_consent=_as_bool(raw.get("whatsapp_consent") or "", False),
        )
        for index, raw in enumerate(reader, start=2)
    ]
    if not rows:
        raise ValueError("Le fichier CSV ne contient aucune ligne")
    errors, warnings = _validate(rows)
    import_id = uuid4()
    _previews[import_id] = StoredPreview(organization_id, rows, errors, warnings)
    return ImportPreview(
        import_id=import_id,
        rows=rows,
        errors=errors,
        warnings=warnings,
        can_commit=not errors,
    )


def update_preview_row(
    organization_id: UUID, import_id: UUID, row_number: int, corrected: ImportRow
) -> ImportPreview:
    preview = get_preview(organization_id, import_id)
    index = next((i for i, row in enumerate(preview.rows) if row.row == row_number), None)
    if index is None:
        raise KeyError("Ligne introuvable")
    corrected.row = row_number
    preview.rows[index] = corrected
    preview.errors, preview.warnings = _validate(preview.rows)
    return ImportPreview(
        import_id=import_id,
        rows=preview.rows,
        errors=preview.errors,
        warnings=preview.warnings,
        can_commit=not preview.errors,
    )


def get_preview(organization_id: UUID, import_id: UUID) -> StoredPreview:
    preview = _previews.get(import_id)
    if preview is None or preview.organization_id != organization_id:
        raise KeyError("Prévisualisation introuvable ou expirée")
    return preview


def commit_preview(db: Session, organization_id: UUID, import_id: UUID) -> tuple[int, int, int]:
    preview = get_preview(organization_id, import_id)
    if preview.errors:
        raise ValueError("Corrigez les erreurs avant de confirmer")
    imported = updated = 0
    try:
        for row in preview.rows:
            volunteer = db.scalar(
                select(Volunteer).where(
                    Volunteer.organization_id == organization_id,
                    Volunteer.email == row.email,
                )
            )
            if volunteer is None:
                volunteer = Volunteer(organization_id=organization_id, email=row.email)
                db.add(volunteer)
                imported += 1
            else:
                updated += 1
            volunteer.display_name = row.display_name
            volunteer.phone_e164 = row.phone_e164 or None
            volunteer.email_consent = row.email_consent
            volunteer.whatsapp_consent = row.whatsapp_consent
            db.flush()
            db.execute(delete(VolunteerSkill).where(VolunteerSkill.volunteer_id == volunteer.id))
            db.execute(
                delete(VolunteerAvailability).where(
                    VolunteerAvailability.volunteer_id == volunteer.id
                )
            )
            db.add_all(
                VolunteerSkill(
                    organization_id=organization_id,
                    volunteer_id=volunteer.id,
                    skill_name=skill,
                )
                for skill in row.skills
            )
            if row.available:
                start = datetime.combine(
                    datetime.now(UTC).date() + timedelta(days=7), datetime.min.time(), UTC
                )
                db.add(
                    VolunteerAvailability(
                        organization_id=organization_id,
                        volunteer_id=volunteer.id,
                        starts_at=start.replace(hour=7),
                        ends_at=start.replace(hour=18),
                    )
                )
        db.commit()
    except Exception:
        db.rollback()
        raise
    _previews.pop(import_id, None)
    total = db.scalar(
        select(func.count()).select_from(Volunteer).where(Volunteer.organization_id == organization_id)
    )
    return imported, updated, int(total or 0)


DEMO_VOLUNTEERS = [
    ("Amina N.", "amina@neighborlink.test", "accueil|premiers secours"),
    ("Boris E.", "boris@neighborlink.test", "logistique|conduite"),
    ("Carine M.", "carine@neighborlink.test", "distribution|accueil"),
    ("David T.", "david@neighborlink.test", "logistique"),
    ("Estelle K.", "estelle@neighborlink.test", "premiers secours"),
    ("Fabrice O.", "fabrice@neighborlink.test", "distribution"),
    ("Grace B.", "grace@neighborlink.test", "accueil"),
    ("Hervé L.", "herve@neighborlink.test", "conduite|logistique"),
    ("Inès S.", "ines@neighborlink.test", "distribution|premiers secours"),
    ("Junior P.", "junior@neighborlink.test", "logistique"),
    ("Kenza D.", "kenza@neighborlink.test", "accueil|distribution"),
    ("Lionel W.", "lionel@neighborlink.test", "conduite"),
]


def seed_demo(db: Session, organization_id: UUID) -> tuple[Operation, int, list[str]]:
    operation = db.scalar(
        select(Operation).where(
            Operation.organization_id == organization_id,
            Operation.name == "Distribution alimentaire de Bonamoussadi",
        )
    )
    roles = ["Accueil", "Logistique", "Distribution", "Premiers secours"]
    if operation is None:
        event_date = datetime.now(UTC).date() + timedelta(days=7)
        operation = Operation(
            organization_id=organization_id,
            name="Distribution alimentaire de Bonamoussadi",
            event_date=event_date,
            location_name="Bonamoussadi, Douala",
            latitude=4.089,
            longitude=9.739,
            status="ready",
        )
        db.add(operation)
        db.flush()
        start = datetime.combine(event_date, datetime.min.time(), UTC).replace(hour=8)
        for offset, role in enumerate(roles):
            db.add(
                Shift(
                    organization_id=organization_id,
                    operation_id=operation.id,
                    name=f"{role} matin",
                    role_name=role,
                    required_skill=role.lower(),
                    starts_at=start + timedelta(minutes=30 * offset),
                    ends_at=start + timedelta(hours=4),
                    capacity=3,
                )
            )
    csv_text = "display_name,email,skills,available,email_consent\n" + "\n".join(
        f"{name},{email},{skills},true,true" for name, email, skills in DEMO_VOLUNTEERS
    )
    preview = parse_preview(organization_id, csv_text.encode())
    if preview.errors:
        raise ValueError("Le scénario de démonstration est invalide")
    commit_preview(db, organization_id, preview.import_id)
    db.commit()
    total = db.scalar(
        select(func.count()).select_from(Volunteer).where(Volunteer.organization_id == organization_id)
    )
    return operation, int(total or 0), roles
