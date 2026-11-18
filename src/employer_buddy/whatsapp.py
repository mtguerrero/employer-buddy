"""Cliente mínimo de WhatsApp Cloud API: firma del webhook, lectura de mensajes y envío."""

import hashlib
import hmac
from dataclasses import dataclass
from typing import Any

import httpx

from employer_buddy.config import Settings


def verify_signature(app_secret: str, body: bytes, header: str | None) -> bool:
    """Comprueba la cabecera X-Hub-Signature-256 que Meta firma con el secreto de la app."""
    if not app_secret or not header:
        return False
    expected = "sha256=" + hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header)


@dataclass(frozen=True)
class InboundMessage:
    wa_message_id: str
    sender: str
    kind: str
    text: str | None
    raw: dict[str, Any]


def parse_inbound(payload: dict[str, Any]) -> list[InboundMessage]:
    """Extrae los mensajes de un webhook. Ignora notificaciones de estado (entregado, leído)."""
    messages: list[InboundMessage] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            for m in change.get("value", {}).get("messages", []) or []:
                kind = m.get("type", "unknown")
                if kind == "text":
                    text = m.get("text", {}).get("body")
                else:
                    text = (m.get(kind) or {}).get("caption")
                messages.append(InboundMessage(m["id"], m["from"], kind, text, m))
    return messages


@dataclass(frozen=True)
class Media:
    content: bytes
    mime_type: str


def _api(settings: Settings, path: str) -> str:
    return f"{settings.whatsapp_api_base}/{settings.whatsapp_api_version}/{path}"


class WhatsAppClient:
    def __init__(self, settings: Settings, http: httpx.Client | None = None) -> None:
        self._settings = settings
        self._http = http or httpx.Client(timeout=15)

    def send_text(self, to: str, body: str) -> str:
        """Envía un mensaje de texto y devuelve el id que asigna WhatsApp."""
        s = self._settings
        url = (
            f"{s.whatsapp_api_base}/{s.whatsapp_api_version}/{s.whatsapp_phone_number_id}/messages"
        )
        response = self._http.post(
            url,
            headers={"Authorization": f"Bearer {s.whatsapp_token}"},
            json={
                "messaging_product": "whatsapp",
                "to": to,
                "type": "text",
                "text": {"body": body},
            },
        )
        response.raise_for_status()
        return response.json()["messages"][0]["id"]

    def download_media(self, media_id: str) -> Media:
        """Descarga un archivo que el usuario envió (documento o imagen)."""
        auth = {"Authorization": f"Bearer {self._settings.whatsapp_token}"}
        meta = self._http.get(_api(self._settings, media_id), headers=auth)
        meta.raise_for_status()
        info = meta.json()
        file = self._http.get(info["url"], headers=auth)
        file.raise_for_status()
        return Media(content=file.content, mime_type=info.get("mime_type", ""))
