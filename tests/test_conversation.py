import io
import itertools

import httpx
import pytest
import respx
from docx import Document
from sqlalchemy import select

from employer_buddy import conversation as conv
from employer_buddy.conversation import Deps
from employer_buddy.documents import DOCX, UnsupportedFileError, to_source
from employer_buddy.jobs import process_one
from employer_buddy.models import LlmUsage, Message, Profile, StoredFile
from employer_buddy.whatsapp import WhatsAppClient
from tests.fakes import FakeAI
from tests.helpers import media_payload, signed, text_payload

GRAPH = "https://graph.facebook.com/v21.0"
PDF_BYTES = b"%PDF-1.4 hoja de vida de ejemplo"
LONG_TEXT = "Trabajo como analista de datos en Empresa Ejemplo desde 2021. " * 5


@pytest.fixture
def wa_send():
    ids = itertools.count(1)
    with respx.mock(assert_all_called=False) as router:
        router.post(f"{GRAPH}/123456/messages").mock(
            side_effect=lambda _req: httpx.Response(
                200, json={"messages": [{"id": f"wamid.out{next(ids)}"}]}
            )
        )
        yield router


def deliver(client, payload):
    body, headers = signed(payload)
    assert client.post("/webhook", content=body, headers=headers).status_code == 200


def outgoing(session) -> list[str]:
    rows = session.scalars(select(Message).where(Message.direction == "out").order_by(Message.id))
    return [m.body for m in rows]


def run(session, settings, ai):
    assert process_one(session, Deps(whatsapp=WhatsAppClient(settings), ai=ai))


def test_saludo_si_no_hay_perfil(client, session, settings, wa_send):
    ai = FakeAI()
    deliver(client, text_payload(body="Hola"))
    run(session, settings, ai)
    assert outgoing(session) == [conv.WELCOME]
    assert ai.calls == []


def test_trayectoria_escrita_crea_el_perfil(client, session, settings, wa_send):
    ai = FakeAI(questions=["¿Qué cargo buscas?", "¿En qué ciudad quieres trabajar?"])
    deliver(client, text_payload(body=LONG_TEXT))
    run(session, settings, ai)

    kind, source, current = ai.calls[0]
    assert kind == "extract" and source.text == LONG_TEXT.strip() and current is None
    profile = session.scalar(select(Profile))
    assert profile.data["full_name"] == "Persona de Ejemplo"
    assert profile.pending_questions == ["¿Qué cargo buscas?", "¿En qué ciudad quieres trabajar?"]
    summary, question = outgoing(session)
    assert "Analista de datos en Empresa Ejemplo (2021-03 - actual)" in summary
    assert question.endswith("¿Qué cargo buscas?") and "me quedan 1 más" in question
    usage = session.scalar(select(LlmUsage))
    assert (usage.purpose, usage.input_tokens, usage.output_tokens) == (
        "extract_profile",
        1000,
        200,
    )


def test_pdf_por_whatsapp(client, session, settings, wa_send):
    wa_send.get(f"{GRAPH}/media-1").mock(
        return_value=httpx.Response(
            200, json={"url": "https://lookaside.example/media-1", "mime_type": "application/pdf"}
        )
    )
    wa_send.get("https://lookaside.example/media-1").mock(
        return_value=httpx.Response(200, content=PDF_BYTES)
    )
    ai = FakeAI(questions=[])
    deliver(client, media_payload())
    run(session, settings, ai)

    _, source, _ = ai.calls[0]
    assert source.mime_type == "application/pdf" and source.content == PDF_BYTES
    stored = session.scalar(select(StoredFile))
    assert stored.content == PDF_BYTES and stored.filename == "hv.pdf"
    replies = outgoing(session)
    assert replies[0] == conv.READING
    assert replies[-1] == conv.PROFILE_COMPLETE


def test_formato_no_soportado(client, session, settings, wa_send):
    wa_send.get(f"{GRAPH}/media-1").mock(
        return_value=httpx.Response(
            200, json={"url": "https://lookaside.example/media-1", "mime_type": "application/zip"}
        )
    )
    wa_send.get("https://lookaside.example/media-1").mock(
        return_value=httpx.Response(200, content=b"PK")
    )
    ai = FakeAI()
    deliver(client, media_payload(mime="application/zip"))
    run(session, settings, ai)
    assert outgoing(session) == [conv.UNSUPPORTED]
    assert ai.calls == []
    assert session.scalar(select(StoredFile)) is None


def test_respuesta_completa_el_perfil(client, session, settings, wa_send):
    ai = FakeAI(questions=["¿Qué cargo buscas?", "¿En qué ciudad quieres trabajar?"])
    deliver(client, text_payload(body=LONG_TEXT, msg_id="wamid.a"))
    run(session, settings, ai)
    deliver(client, text_payload(body="Analista de BI", msg_id="wamid.b"))
    run(session, settings, ai)

    assert ai.calls[1] == ("apply_answer", "¿Qué cargo buscas?", "Analista de BI")
    profile = session.scalar(select(Profile))
    session.refresh(profile)
    assert profile.data["preferences"]["target_roles"] == ["Analista de BI"]
    assert profile.pending_questions == ["¿En qué ciudad quieres trabajar?"]
    assert outgoing(session)[-1].endswith("¿En qué ciudad quieres trabajar?")
    assert session.query(LlmUsage).count() == 2


def test_rechazo_del_modelo(client, session, settings, wa_send):
    deliver(client, text_payload(body=LONG_TEXT))
    run(session, settings, FakeAI(refuse=True))
    assert outgoing(session) == [conv.REFUSED]
    assert session.scalar(select(Profile)) is None


def test_docx_se_convierte_a_texto():
    doc = Document()
    doc.add_paragraph("Analista de datos - Empresa Ejemplo")
    table = doc.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "2021"
    table.rows[0].cells[1].text = "SQL"
    buffer = io.BytesIO()
    doc.save(buffer)

    source = to_source(buffer.getvalue(), DOCX)
    assert source.mime_type == "text/plain"
    assert "Analista de datos - Empresa Ejemplo" in source.text
    assert "2021 | SQL" in source.text


def test_archivo_desconocido():
    with pytest.raises(UnsupportedFileError):
        to_source(b"x", "application/zip")
