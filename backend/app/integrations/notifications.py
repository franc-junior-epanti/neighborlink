import base64
import time
from email.mime.text import MIMEText
from typing import TYPE_CHECKING, Protocol

import httpx

from app.config import Settings

if TYPE_CHECKING:
    from app.models import NotificationOutbox

GMAIL_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"


class NotificationAdapter(Protocol):
    def send(self, outbox: "NotificationOutbox") -> bool: ...


class SimulatedAdapter:
    """Default adapter used when no real credentials are configured for a channel."""

    def send(self, outbox: "NotificationOutbox") -> bool:
        return True


class GmailAdapter:
    """Sends real email through the Gmail API using an OAuth2 refresh token."""

    def __init__(self, client_id: str, client_secret: str, refresh_token: str, sender_email: str) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.sender_email = sender_email
        self._access_token: str | None = None
        self._access_token_expiry = 0.0

    def _refresh_access_token(self) -> str:
        if self._access_token and time.monotonic() < self._access_token_expiry:
            return self._access_token
        response = httpx.post(
            GMAIL_TOKEN_URL,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
        self._access_token = payload["access_token"]
        self._access_token_expiry = time.monotonic() + payload.get("expires_in", 3600) - 30
        return self._access_token

    def send(self, outbox: "NotificationOutbox") -> bool:
        access_token = self._refresh_access_token()
        message = MIMEText(outbox.rendered_content)
        message["to"] = outbox.recipient
        message["from"] = self.sender_email
        message["subject"] = "NeighborLink — votre affectation"
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        response = httpx.post(
            GMAIL_SEND_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            json={"raw": raw},
            timeout=10,
        )
        return response.status_code < 300


class InfobipWhatsAppAdapter:
    """Sends real WhatsApp messages through the Infobip WhatsApp API."""

    def __init__(self, base_url: str, api_key: str, sender: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.sender = sender

    def send(self, outbox: "NotificationOutbox") -> bool:
        response = httpx.post(
            f"{self.base_url}/whatsapp/1/message/text",
            headers={
                "Authorization": f"App {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json={
                "from": self.sender,
                "to": outbox.recipient,
                "content": {"text": outbox.rendered_content},
            },
            timeout=10,
        )
        return response.status_code < 300


def build_registry(settings: Settings) -> dict[str, NotificationAdapter]:
    registry: dict[str, NotificationAdapter] = {
        "email": SimulatedAdapter(),
        "whatsapp": SimulatedAdapter(),
    }
    if all([settings.gmail_client_id, settings.gmail_client_secret, settings.gmail_refresh_token, settings.gmail_sender_email]):
        registry["email"] = GmailAdapter(
            settings.gmail_client_id,
            settings.gmail_client_secret,
            settings.gmail_refresh_token,
            settings.gmail_sender_email,
        )
    if all([settings.infobip_base_url, settings.infobip_api_key, settings.infobip_whatsapp_sender]):
        registry["whatsapp"] = InfobipWhatsAppAdapter(
            settings.infobip_base_url,
            settings.infobip_api_key,
            settings.infobip_whatsapp_sender,
        )
    return registry
