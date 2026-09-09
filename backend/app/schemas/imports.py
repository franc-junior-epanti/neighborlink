from uuid import UUID

from pydantic import BaseModel, Field


class ImportIssue(BaseModel):
    row: int
    field: str
    message: str


class ImportRow(BaseModel):
    row: int
    display_name: str = ""
    email: str = ""
    phone_e164: str = ""
    skills: list[str] = Field(default_factory=list)
    available: bool = True
    email_consent: bool = True
    whatsapp_consent: bool = False


class ImportPreview(BaseModel):
    import_id: UUID
    rows: list[ImportRow]
    errors: list[ImportIssue]
    warnings: list[ImportIssue]
    can_commit: bool


class ImportCommitResponse(BaseModel):
    imported: int
    updated: int
    total_volunteers: int


class DemoResponse(BaseModel):
    operation_id: UUID
    volunteers: int
    roles: list[str]
