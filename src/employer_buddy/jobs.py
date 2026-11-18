"""Cola de trabajos sobre PostgreSQL (SELECT ... FOR UPDATE SKIP LOCKED)."""

import logging
from collections.abc import Callable
from datetime import timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from employer_buddy.config import Settings
from employer_buddy.models import Job, Message, User
from employer_buddy.whatsapp import WhatsAppClient

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
STALE_AFTER = timedelta(minutes=10)

WELCOME_TEXT = (
    "¡Hola! Recibí tu mensaje. Muy pronto podré ayudarte a configurar tu perfil "
    "y a adaptar tu hoja de vida a cada vacante que me envíes."
)

Handler = Callable[[Session, Job, WhatsAppClient], None]


def claim_next(session: Session) -> Job | None:
    """Toma el siguiente trabajo pendiente. También recupera trabajos de un worker caído."""
    now = func.now()
    stmt = (
        select(Job)
        .where(
            or_(
                and_(Job.status == "pending", Job.run_after <= now),
                and_(Job.status == "running", Job.updated_at < now - STALE_AFTER),
            )
        )
        .order_by(Job.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    job = session.scalar(stmt)
    if job is None:
        return None
    job.status = "running"
    job.attempts += 1
    session.commit()
    return job


def send_reply(session: Session, user: User, client: WhatsAppClient, text: str) -> None:
    wa_id = client.send_text(user.phone, text)
    session.add(
        Message(user_id=user.id, wa_message_id=wa_id, direction="out", kind="text", body=text)
    )


def handle_message(session: Session, job: Job, client: WhatsAppClient) -> None:
    user = session.get(User, job.user_id)
    assert user is not None
    send_reply(session, user, client, WELCOME_TEXT)


HANDLERS: dict[str, Handler] = {"handle_message": handle_message}


def run_job(session: Session, job: Job, client: WhatsAppClient) -> None:
    handler = HANDLERS.get(job.kind)
    try:
        if handler is None:
            raise ValueError(f"Tipo de trabajo desconocido: {job.kind}")
        handler(session, job, client)
        job.status = "done"
        job.last_error = None
        session.commit()
    except Exception as exc:  # noqa: BLE001 - se registra y se reintenta
        session.rollback()
        job = session.merge(job)
        job.last_error = f"{type(exc).__name__}: {exc}"[:2000]
        if job.attempts >= MAX_ATTEMPTS:
            job.status = "failed"
            log.exception("Trabajo %s falló definitivamente", job.id)
        else:
            job.status = "pending"
            job.run_after = func.now() + timedelta(seconds=10 * 2**job.attempts)
            log.warning("Trabajo %s falló, se reintentará: %s", job.id, exc)
        session.commit()


def process_one(session: Session, settings: Settings, client: WhatsAppClient) -> bool:
    """Procesa un trabajo si hay alguno. Devuelve True si procesó algo."""
    job = claim_next(session)
    if job is None:
        return False
    run_job(session, job, client)
    return True
