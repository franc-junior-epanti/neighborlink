from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.api.session import DatabaseSession
from app.config import get_settings
from app.services.responses import InvalidResponseToken, record_response

router = APIRouter(prefix="/api/v1/public", tags=["public-responses"])


def _page(title: str, message: str) -> HTMLResponse:
    return HTMLResponse(
        f"<!doctype html><html lang=\"fr\"><head><meta charset=\"utf-8\">"
        f"<title>{title}</title></head>"
        f"<body style=\"font-family: sans-serif; padding: 2rem; text-align: center;\">"
        f"<h1>{title}</h1><p>{message}</p></body></html>"
    )


@router.get("/responses/{token}", response_class=HTMLResponse)
def respond(token: str, db: DatabaseSession) -> HTMLResponse:
    settings = get_settings()
    try:
        response = record_response(db, settings.response_signing_secret, token)
    except InvalidResponseToken:
        return _page("Lien invalide", "Ce lien de confirmation n'est plus valide.")
    if response.decision == "confirm":
        return _page("Merci !", "Votre présence a bien été confirmée.")
    return _page("Merci de nous avoir prévenus", "Votre absence a bien été enregistrée.")
