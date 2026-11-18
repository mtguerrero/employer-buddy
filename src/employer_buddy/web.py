"""Página de revisión del perfil."""

import json
from importlib import resources

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from employer_buddy.config import Settings, get_settings
from employer_buddy.db import get_session
from employer_buddy.models import Job, Profile
from employer_buddy.profile_schema import ProfileData
from employer_buddy.review import (
    COOKIE_NAME,
    make_session_cookie,
    read_session_cookie,
    redeem,
)

router = APIRouter()


def _template(name: str) -> str:
    return resources.files("employer_buddy").joinpath(f"templates/{name}").read_text()


def _message_page(title: str, body: str) -> str:
    """Página simple de aviso. Los textos son fijos y pueden llevar HTML."""
    return _template("mensaje.html").replace("__TITLE__", title).replace("__BODY__", body)


EXPIRED = _message_page(
    "Este enlace ya no sirve",
    "Los enlaces se pueden usar una sola vez y vencen después de un tiempo. "
    "Escribe <strong>perfil</strong> en WhatsApp y te envío uno nuevo.",
)


def _page(profile: Profile) -> str:
    template = _template("perfil.html")
    data = {
        "profile": profile.data,
        "status": profile.status,
        "pending_questions": profile.pending_questions,
    }
    # Evita que un "</script>" dentro de los datos cierre la etiqueta.
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    return template.replace("__PROFILE_JSON__", payload)


def _current_user(request: Request, settings: Settings) -> int | None:
    return read_session_cookie(settings, request.cookies.get(COOKIE_NAME))


@router.get("/perfil", response_class=HTMLResponse)
def profile_page(
    request: Request,
    t: str | None = None,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Response:
    if t:
        user_id = redeem(session, t)
        session.commit()
        if user_id is None:
            return HTMLResponse(EXPIRED, status_code=410)
        # Se cambia el enlace por una cookie y se quita el token de la URL.
        response = RedirectResponse("/perfil", status_code=303)
        response.set_cookie(
            COOKIE_NAME,
            make_session_cookie(settings, user_id),
            max_age=settings.review_session_hours * 3600,
            httponly=True,
            secure=not settings.is_development,
            samesite="strict",
        )
        return response

    user_id = _current_user(request, settings)
    if user_id is None:
        return HTMLResponse(EXPIRED, status_code=401)
    profile = session.scalar(select(Profile).where(Profile.user_id == user_id))
    if profile is None:
        return HTMLResponse(
            _message_page(
                "Todavía no tienes perfil",
                "Envíame tu hoja de vida por WhatsApp para empezar.",
            ),
            status_code=404,
        )
    return HTMLResponse(_page(profile), headers={"Cache-Control": "no-store"})


class ProfileSave(BaseModel):
    profile: ProfileData
    confirm: bool = False


@router.put("/api/perfil")
def save_profile(
    body: ProfileSave,
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    user_id = _current_user(request, settings)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Sesión vencida")
    profile = session.scalar(select(Profile).where(Profile.user_id == user_id))
    if profile is None:
        raise HTTPException(status_code=404, detail="Sin perfil")

    profile.data = body.profile.model_dump()
    if body.confirm:
        profile.status = "confirmed"
        profile.pending_questions = []
        session.add(Job(user_id=user_id, kind="profile_confirmed", payload={}))
    else:
        profile.status = "draft"
    session.commit()
    return {"status": profile.status}
