import httpx
import respx
from sqlalchemy import select

from employer_buddy.conversation import WELCOME, Deps
from employer_buddy.jobs import MAX_ATTEMPTS, process_one
from employer_buddy.models import Job, Message
from employer_buddy.whatsapp import WhatsAppClient
from tests.fakes import FakeAI
from tests.helpers import ALLOWED, signed, text_payload

SEND_URL = "https://graph.facebook.com/v21.0/123456/messages"


def enqueue_one(client):
    body, headers = signed(text_payload())
    client.post("/webhook", content=body, headers=headers)


def deps(settings) -> Deps:
    return Deps(whatsapp=WhatsAppClient(settings), ai=FakeAI(), settings=settings)


@respx.mock
def test_worker_responde_por_whatsapp(client, session, settings):
    enqueue_one(client)
    route = respx.post(SEND_URL).mock(
        return_value=httpx.Response(200, json={"messages": [{"id": "wamid.salida"}]})
    )

    assert process_one(session, deps(settings)) is True

    sent = route.calls.last.request
    assert sent.headers["Authorization"] == "Bearer token-falso"
    assert b'"to":"' + ALLOWED.encode() + b'"' in sent.content.replace(b" ", b"")
    out = session.scalar(select(Message).where(Message.direction == "out"))
    assert out.wa_message_id == "wamid.salida" and out.body == WELCOME
    assert session.scalar(select(Job)).status == "done"


def test_sin_trabajos_no_hace_nada(session, settings):
    assert process_one(session, deps(settings)) is False


@respx.mock
def test_error_de_whatsapp_reprograma_el_trabajo(client, session, settings):
    enqueue_one(client)
    respx.post(SEND_URL).mock(return_value=httpx.Response(500))

    process_one(session, deps(settings))

    job = session.scalar(select(Job))
    session.refresh(job)
    assert job.status == "pending"
    assert job.attempts == 1
    assert "HTTPStatusError" in job.last_error
    assert session.scalar(select(Message).where(Message.direction == "out")) is None


@respx.mock
def test_trabajo_falla_tras_maximo_de_intentos(client, session, settings):
    enqueue_one(client)
    respx.post(SEND_URL).mock(return_value=httpx.Response(500))
    job = session.scalar(select(Job))
    job.attempts = MAX_ATTEMPTS - 1
    session.commit()

    process_one(session, deps(settings))

    session.refresh(job)
    assert job.status == "failed"


class BrokeAI(FakeAI):
    def extract(self, source, current):
        import anthropic
        import httpx as _httpx

        request = _httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        raise anthropic.BadRequestError(
            "credit balance is too low",
            response=_httpx.Response(400, request=request),
            body=None,
        )


@respx.mock
def test_error_no_recuperable_no_se_reintenta(client, session, settings):
    respx.post(SEND_URL).mock(
        return_value=httpx.Response(200, json={"messages": [{"id": "wamid.x"}]})
    )
    body, headers = signed(text_payload(body="Trabajo como analista de datos. " * 10))
    client.post("/webhook", content=body, headers=headers)

    process_one(session, Deps(whatsapp=WhatsAppClient(settings), ai=BrokeAI(), settings=settings))

    job = session.scalar(select(Job))
    session.refresh(job)
    assert job.status == "failed" and job.attempts == 1
