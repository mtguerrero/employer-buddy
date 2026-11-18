"""Cola de trabajos sobre PostgreSQL (SELECT ... FOR UPDATE SKIP LOCKED)."""

import logging
from collections.abc import Callable
from datetime import timedelta

import anthropic
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from employer_buddy import conversation
from employer_buddy.conversation import Deps
from employer_buddy.models import Job, User

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
STALE_AFTER = timedelta(minutes=10)

# Errores que no se arreglan reintentando (clave inválida, sin saldo, solicitud mal formada).
NON_RETRYABLE = (
    anthropic.BadRequestError,
    anthropic.AuthenticationError,
    anthropic.PermissionDeniedError,
)

Handler = Callable[[Session, Job, Deps], None]


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


def handle_message(session: Session, job: Job, deps: Deps) -> None:
    user = session.get(User, job.user_id)
    assert user is not None
    conversation.handle_message(session, user, deps, job.payload["wa_message_id"])


def profile_confirmed(session: Session, job: Job, deps: Deps) -> None:
    user = session.get(User, job.user_id)
    assert user is not None
    conversation.handle_profile_confirmed(session, user, deps)


HANDLERS: dict[str, Handler] = {
    "handle_message": handle_message,
    "profile_confirmed": profile_confirmed,
}


def run_job(session: Session, job: Job, deps: Deps) -> None:
    handler = HANDLERS.get(job.kind)
    try:
        if handler is None:
            raise ValueError(f"Tipo de trabajo desconocido: {job.kind}")
        handler(session, job, deps)
        job.status = "done"
        job.last_error = None
        session.commit()
    except Exception as exc:  # noqa: BLE001 - se registra y se reintenta
        session.rollback()
        job = session.merge(job)
        job.last_error = f"{type(exc).__name__}: {exc}"[:2000]
        if job.attempts >= MAX_ATTEMPTS or isinstance(exc, NON_RETRYABLE):
            job.status = "failed"
            log.exception("Trabajo %s falló definitivamente", job.id)
        else:
            job.status = "pending"
            job.run_after = func.now() + timedelta(seconds=10 * 2**job.attempts)
            log.warning("Trabajo %s falló, se reintentará: %s", job.id, exc)
        session.commit()


def process_one(session: Session, deps: Deps) -> bool:
    """Procesa un trabajo si hay alguno. Devuelve True si procesó algo."""
    job = claim_next(session)
    if job is None:
        return False
    run_job(session, job, deps)
    return True
