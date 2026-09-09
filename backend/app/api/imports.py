from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.api.session import CurrentIdentity, DatabaseSession
from app.repositories.session import get_membership, synchronize_user
from app.schemas.imports import DemoResponse, ImportCommitResponse, ImportPreview, ImportRow
from app.services.imports import commit_preview, parse_preview, seed_demo, update_preview_row

router = APIRouter(prefix="/api/v1/organizations/{organization_id}", tags=["imports"])


def allowed_organization(
    organization_id: UUID,
    identity: CurrentIdentity,
    db: DatabaseSession,
) -> UUID:
    user = synchronize_user(db, identity)
    if get_membership(db, user.id, organization_id) is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Association interdite")
    return organization_id


AllowedOrganization = Annotated[UUID, Depends(allowed_organization)]


@router.post("/imports/volunteers/preview", response_model=ImportPreview)
async def preview_volunteers(
    organization_id: AllowedOrganization,
    file: Annotated[UploadFile, File()],
) -> ImportPreview:
    try:
        return parse_preview(organization_id, await file.read())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/imports/{import_id}/rows/{row_number}", response_model=ImportPreview)
def correct_preview_row(
    organization_id: AllowedOrganization,
    import_id: UUID,
    row_number: int,
    payload: ImportRow,
) -> ImportPreview:
    try:
        return update_preview_row(organization_id, import_id, row_number, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/imports/{import_id}/commit", response_model=ImportCommitResponse)
def confirm_import(
    organization_id: AllowedOrganization,
    import_id: UUID,
    db: DatabaseSession,
) -> ImportCommitResponse:
    try:
        imported, updated, total = commit_preview(db, organization_id, import_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ImportCommitResponse(imported=imported, updated=updated, total_volunteers=total)


@router.post("/demo", response_model=DemoResponse)
def load_demo(
    organization_id: AllowedOrganization,
    db: DatabaseSession,
) -> DemoResponse:
    operation, volunteers, roles = seed_demo(db, organization_id)
    return DemoResponse(operation_id=operation.id, volunteers=volunteers, roles=roles)
