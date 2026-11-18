import itertools
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx
from sqlalchemy import select

from employer_buddy import conversation as conv
from employer_buddy.conversation import Deps
from employer_buddy.jobs import process_one
from employer_buddy.models import Job, Message, Profile, ReviewToken, User
from employer_buddy.review import (
    COOKIE_NAME,
    create_review_link,
    make_session_cookie,
    read_session_cookie,
)
from employer_buddy.whatsapp import WhatsAppClient
from tests.fakes import FakeAI, sample_profile
from tests.helpers import ALLOWED, signed, text_payload

GRAPH = "https://graph.facebook.com/v21.0"


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


@pytest.fixture
def user_with_profile(session):
    user = User(phone=ALLOWED)
    session.add(user)
    session.flush()
    session.add(Profile(user_id=user.id, data=sample_profile().model_dump(), pending_questions=[]))
    session.commit()
    return user


def token_from(link: str) -> str:
    return link.split("t=", 1)[1]


def test_enlace_abre_sesion_y_solo_sirve_una_vez(client, session, settings, user_with_profile):
    link = create_review_link(session, settings, user_with_profile)
    session.commit()

    first = client.get(f"/perfil?t={token_from(link)}", follow_redirects=False)
    assert first.status_code == 303 and first.headers["location"] == "/perfil"
    cookie = first.cookies.get(COOKIE_NAME)
    assert read_session_cookie(settings, cookie) == user_with_profile.id

    client.cookies.set(COOKIE_NAME, cookie)
    page = client.get("/perfil")
    client.cookies.clear()
    assert page.status_code == 200
    assert "Persona de Ejemplo" in page.text
    assert "__PROFILE_JSON__" not in page.text

    again = client.get(f"/perfil?t={token_from(link)}", follow_redirects=False)
    assert again.status_code == 410


def test_enlace_vencido(client, session, settings, user_with_profile):
    link = create_review_link(session, settings, user_with_profile)
    row = session.scalar(select(ReviewToken))
    row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    session.commit()
    assert client.get(f"/perfil?t={token_from(link)}").status_code == 410


def test_sin_sesion_no_muestra_el_perfil(client):
    assert client.get("/perfil").status_code == 401
    client.cookies.set(COOKIE_NAME, "1.9999999999.firma")
    assert client.get("/perfil").status_code == 401


def test_la_base_de_datos_no_guarda_el_token(session, settings, user_with_profile):
    link = create_review_link(session, settings, user_with_profile)
    assert token_from(link) not in session.scalar(select(ReviewToken)).token_hash


def test_guardar_y_confirmar(client, session, settings, user_with_profile):
    cookies = {COOKIE_NAME: make_session_cookie(settings, user_with_profile.id)}
    client.cookies.update(cookies)
    edited = sample_profile()
    edited.links = ["https://linkedin.com/in/ejemplo"]

    saved = client.put("/api/perfil", json={"profile": edited.model_dump(), "confirm": False})
    assert saved.json() == {"status": "draft"}
    assert session.scalar(select(Job)) is None

    confirmed = client.put("/api/perfil", json={"profile": edited.model_dump(), "confirm": True})
    assert confirmed.json() == {"status": "confirmed"}
    profile = session.scalar(select(Profile))
    session.refresh(profile)
    assert profile.data["links"] == ["https://linkedin.com/in/ejemplo"]
    assert profile.status == "confirmed"
    assert session.scalar(select(Job)).kind == "profile_confirmed"


def test_datos_invalidos_se_rechazan(client, settings, user_with_profile):
    cookies = {COOKIE_NAME: make_session_cookie(settings, user_with_profile.id)}
    client.cookies.update(cookies)
    bad = client.put("/api/perfil", json={"profile": {"full_name": 3}})
    assert bad.status_code == 422


def test_guardar_sin_sesion(client):
    payload = {"profile": sample_profile().model_dump(), "confirm": True}
    assert client.put("/api/perfil", json=payload).status_code == 401


def test_escribir_perfil_envia_enlace(client, session, settings, user_with_profile, wa_send):
    body, headers = signed(text_payload(body="Perfil"))
    client.post("/webhook", content=body, headers=headers)
    deps = Deps(whatsapp=WhatsAppClient(settings), ai=FakeAI(), settings=settings)
    process_one(session, deps)

    out = session.scalar(select(Message).where(Message.direction == "out"))
    assert "/perfil?t=" in out.body
    assert session.scalar(select(ReviewToken)) is not None


def test_confirmacion_avisa_por_whatsapp(client, session, settings, user_with_profile, wa_send):
    session.add(Job(user_id=user_with_profile.id, kind="profile_confirmed", payload={}))
    session.commit()
    deps = Deps(whatsapp=WhatsAppClient(settings), ai=FakeAI(), settings=settings)
    process_one(session, deps)
    out = session.scalar(select(Message).where(Message.direction == "out"))
    assert out.body == conv.PROFILE_CONFIRMED


def test_secreto_de_ejemplo_no_sirve_en_produccion(settings):
    prod = settings.model_copy(update={"app_env": "production"})
    with pytest.raises(RuntimeError):
        prod.check()
