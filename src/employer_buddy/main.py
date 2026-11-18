"""API web: webhook de WhatsApp. Responde rápido y deja el trabajo en la cola."""

import hmac
import json
import logging

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from employer_buddy.config import Settings, get_settings
from employer_buddy.db import get_session
from employer_buddy.inbox import handle_inbound
from employer_buddy.whatsapp import parse_inbound, verify_signature

log = logging.getLogger(__name__)

app = FastAPI(title="Asistente de postulaciones")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/webhook", response_class=PlainTextResponse)
def verify_webhook(
    mode: str = Query("", alias="hub.mode"),
    token: str = Query("", alias="hub.verify_token"),
    challenge: str = Query("", alias="hub.challenge"),
    settings: Settings = Depends(get_settings),
) -> str:
    """Meta llama a este endpoint una vez al registrar el webhook."""
    expected = settings.whatsapp_verify_token
    if mode == "subscribe" and expected and hmac.compare_digest(token, expected):
        return challenge
    raise HTTPException(status_code=403, detail="Token de verificación inválido")


@app.post("/webhook")
async def receive_webhook(
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    body = await request.body()
    if not verify_signature(
        settings.whatsapp_app_secret, body, request.headers.get("X-Hub-Signature-256")
    ):
        raise HTTPException(status_code=403, detail="Firma inválida")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="JSON inválido") from exc

    for msg in parse_inbound(payload):
        handle_inbound(session, settings, msg)
    session.commit()
    return {"status": "ok"}
