"""Enlaces de un solo uso y sesión firmada para la página de revisión del perfil."""

import hashlib
import hmac
import secrets
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from employer_buddy.config import Settings
from employer_buddy.models import ReviewToken, User

COOKIE_NAME = "eb_session"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_review_link(session: Session, settings: Settings, user: User) -> str:
    token = secrets.token_urlsafe(32)
    session.add(
        ReviewToken(
            user_id=user.id,
            token_hash=_hash(token),
            expires_at=datetime.now(UTC) + timedelta(hours=settings.review_link_hours),
        )
    )
    session.flush()
    return f"{settings.public_base_url.rstrip('/')}/perfil?t={token}"


def redeem(session: Session, token: str) -> int | None:
    """Marca el enlace como usado y devuelve el usuario. None si no sirve."""
    row = session.scalar(
        select(ReviewToken).where(ReviewToken.token_hash == _hash(token)).with_for_update()
    )
    now = datetime.now(UTC)
    if row is None or row.used_at is not None or row.expires_at <= now:
        return None
    row.used_at = now
    return row.user_id


def _sign(secret: str, payload: str) -> str:
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def make_session_cookie(settings: Settings, user_id: int) -> str:
    expires = int(time.time()) + settings.review_session_hours * 3600
    payload = f"{user_id}.{expires}"
    return f"{payload}.{_sign(settings.session_secret, payload)}"


def read_session_cookie(settings: Settings, value: str | None) -> int | None:
    if not value:
        return None
    try:
        user_id, expires, signature = value.split(".")
        payload = f"{user_id}.{expires}"
        if not hmac.compare_digest(signature, _sign(settings.session_secret, payload)):
            return None
        if int(expires) < time.time():
            return None
        return int(user_id)
    except ValueError:
        return None
