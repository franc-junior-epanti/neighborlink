from types import SimpleNamespace

import httpx
import pytest

from app.config import Settings
from app.integrations.notifications import (
    GmailAdapter,
    InfobipWhatsAppAdapter,
    SimulatedAdapter,
    build_registry,
)


def _outbox(recipient: str = "volunteer@test.dev", content: str = "Bonjour") -> SimpleNamespace:
    return SimpleNamespace(recipient=recipient, rendered_content=content)


def test_simulated_adapter_always_succeeds() -> None:
    assert SimulatedAdapter().send(_outbox()) is True


def test_build_registry_defaults_to_simulated_without_credentials() -> None:
    registry = build_registry(Settings())
    assert isinstance(registry["email"], SimulatedAdapter)
    assert isinstance(registry["whatsapp"], SimulatedAdapter)


def test_build_registry_picks_gmail_when_fully_configured() -> None:
    settings = Settings(
        gmail_client_id="id",
        gmail_client_secret="secret",
        gmail_refresh_token="refresh",
        gmail_sender_email="sender@test.dev",
    )
    registry = build_registry(settings)
    assert isinstance(registry["email"], GmailAdapter)
    assert isinstance(registry["whatsapp"], SimulatedAdapter)


def test_build_registry_requires_all_gmail_fields() -> None:
    settings = Settings(gmail_client_id="id", gmail_sender_email="sender@test.dev")
    registry = build_registry(settings)
    assert isinstance(registry["email"], SimulatedAdapter)


def test_build_registry_picks_infobip_when_fully_configured() -> None:
    settings = Settings(
        infobip_base_url="https://api.infobip.com",
        infobip_api_key="key",
        infobip_whatsapp_sender="+237000000",
    )
    registry = build_registry(settings)
    assert isinstance(registry["whatsapp"], InfobipWhatsAppAdapter)
    assert isinstance(registry["email"], SimulatedAdapter)


def _response(status: int, url: str, **json_kwargs) -> httpx.Response:
    return httpx.Response(status, request=httpx.Request("POST", url), **json_kwargs)


def test_gmail_adapter_sends_via_api(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        if "oauth2.googleapis.com" in url:
            return _response(200, url, json={"access_token": "tok", "expires_in": 3600})
        return _response(200, url, json={"id": "msg-1"})

    monkeypatch.setattr(httpx, "post", fake_post)

    adapter = GmailAdapter("client", "secret", "refresh", "sender@test.dev")
    assert adapter.send(_outbox()) is True
    assert len(calls) == 2
    assert calls[0][0] == "https://oauth2.googleapis.com/token"
    assert calls[1][0] == "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
    assert calls[1][1]["headers"]["Authorization"] == "Bearer tok"


def test_gmail_adapter_caches_access_token(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_post(url, **kwargs):
        calls.append(url)
        if "oauth2.googleapis.com" in url:
            return _response(200, url, json={"access_token": "tok", "expires_in": 3600})
        return _response(200, url, json={"id": "msg-1"})

    monkeypatch.setattr(httpx, "post", fake_post)

    adapter = GmailAdapter("client", "secret", "refresh", "sender@test.dev")
    adapter.send(_outbox())
    adapter.send(_outbox())
    token_calls = [c for c in calls if "oauth2.googleapis.com" in c]
    assert len(token_calls) == 1


def test_gmail_adapter_reports_failure_on_error_status(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_post(url, **kwargs):
        if "oauth2.googleapis.com" in url:
            return _response(200, url, json={"access_token": "tok", "expires_in": 3600})
        return _response(500, url, json={"error": "boom"})

    monkeypatch.setattr(httpx, "post", fake_post)

    adapter = GmailAdapter("client", "secret", "refresh", "sender@test.dev")
    assert adapter.send(_outbox()) is False


def test_infobip_adapter_sends_whatsapp_message(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(200, json={"messages": []})

    monkeypatch.setattr(httpx, "post", fake_post)

    adapter = InfobipWhatsAppAdapter("https://api.infobip.com", "key", "+237000000")
    outbox = _outbox(recipient="+237111111", content="Confirmez svp")
    assert adapter.send(outbox) is True
    url, kwargs = calls[0]
    assert url == "https://api.infobip.com/whatsapp/1/message/text"
    assert kwargs["headers"]["Authorization"] == "App key"
    assert kwargs["json"]["to"] == "+237111111"
    assert kwargs["json"]["content"]["text"] == "Confirmez svp"


def test_infobip_adapter_reports_failure_on_error_status(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "post", lambda url, **kwargs: httpx.Response(400, json={}))

    adapter = InfobipWhatsAppAdapter("https://api.infobip.com", "key", "+237000000")
    assert adapter.send(_outbox()) is False
