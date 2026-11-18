"""Registro de mensajes entrantes y creación de trabajos."""

import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from employer_buddy.config import Settings
from employer_buddy.models import Job, Message, User
from employer_buddy.whatsapp import InboundMessage

log = logging.getLogger(__name__)


def get_or_create_user(session: Session, phone: str) -> User:
    user = session.scalar(select(User).where(User.phone == phone))
    if user is None:
        user = User(phone=phone)
        session.add(user)
        session.flush()
    return user


def handle_inbound(session: Session, settings: Settings, msg: InboundMessage) -> Job | None:
    """Guarda el mensaje y encola su procesamiento.

    Devuelve None si el número no está autorizado o si el mensaje ya se había recibido
    (Meta reintenta el webhook cuando no recibe respuesta a tiempo).
    """
    if msg.sender not in settings.allowed_number_set:
        # No se guarda nada de números no autorizados.
        log.info("Mensaje ignorado: número no autorizado")
        return None

    user = get_or_create_user(session, msg.sender)
    try:
        with session.begin_nested():
            session.add(
                Message(
                    user_id=user.id,
                    wa_message_id=msg.wa_message_id,
                    direction="in",
                    kind=msg.kind,
                    body=msg.text,
                    raw=msg.raw,
                )
            )
    except IntegrityError:
        log.info("Mensaje duplicado ignorado: %s", msg.wa_message_id)
        return None

    job = Job(user_id=user.id, kind="handle_message", payload={"wa_message_id": msg.wa_message_id})
    session.add(job)
    session.flush()
    return job
