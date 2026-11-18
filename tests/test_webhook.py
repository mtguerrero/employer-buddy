from sqlalchemy import func, select

from employer_buddy.models import Job, Message, User
from tests.helpers import signed, text_payload


def count(session, model) -> int:
    return session.scalar(select(func.count()).select_from(model))


def test_verificacion_del_webhook(client):
    r = client.get(
        "/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "token-de-verificacion",
            "hub.challenge": "abc123",
        },
    )
    assert r.status_code == 200
    assert r.text == "abc123"


def test_verificacion_con_token_incorrecto(client):
    r = client.get(
        "/webhook",
        params={"hub.mode": "subscribe", "hub.verify_token": "otro", "hub.challenge": "x"},
    )
    assert r.status_code == 403


def test_rechaza_firma_invalida(client, session):
    body, headers = signed(text_payload())
    headers["X-Hub-Signature-256"] = "sha256=" + "0" * 64
    r = client.post("/webhook", content=body, headers=headers)
    assert r.status_code == 403
    assert count(session, Message) == 0


def test_guarda_mensaje_y_encola_trabajo(client, session):
    body, headers = signed(text_payload(body="Quiero configurar mi perfil"))
    r = client.post("/webhook", content=body, headers=headers)
    assert r.status_code == 200

    msg = session.scalar(select(Message))
    assert msg.direction == "in" and msg.body == "Quiero configurar mi perfil"
    job = session.scalar(select(Job))
    assert job.kind == "handle_message" and job.status == "pending"
    assert job.user_id == msg.user_id


def test_ignora_reintentos_del_mismo_mensaje(client, session):
    body, headers = signed(text_payload(msg_id="wamid.repetido"))
    client.post("/webhook", content=body, headers=headers)
    r = client.post("/webhook", content=body, headers=headers)
    assert r.status_code == 200
    assert count(session, Message) == 1
    assert count(session, Job) == 1


def test_no_guarda_nada_de_numeros_no_autorizados(client, session):
    body, headers = signed(text_payload(sender="15550001111"))
    r = client.post("/webhook", content=body, headers=headers)
    assert r.status_code == 200
    assert count(session, User) == 0
    assert count(session, Message) == 0
    assert count(session, Job) == 0


def test_ignora_notificaciones_de_estado(client, session):
    payload = text_payload()
    value = payload["entry"][0]["changes"][0]["value"]
    del value["messages"]
    value["statuses"] = [{"id": "wamid.x", "status": "read"}]
    body, headers = signed(payload)
    assert client.post("/webhook", content=body, headers=headers).status_code == 200
    assert count(session, Job) == 0
