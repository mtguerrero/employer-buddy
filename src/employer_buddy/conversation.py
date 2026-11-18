"""Lógica de la conversación de la fase A: construir y completar el perfil maestro."""

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from employer_buddy.ai import AIRefusalError, AIResult, ProfileAI, SourceDocument
from employer_buddy.config import Settings
from employer_buddy.documents import UnsupportedFileError, to_source
from employer_buddy.models import LlmUsage, Message, Profile, StoredFile, User
from employer_buddy.profile_schema import ProfileData
from employer_buddy.review import create_review_link
from employer_buddy.whatsapp import WhatsAppClient

log = logging.getLogger(__name__)

# Un texto más largo que esto, sin perfil todavía, se trata como la trayectoria escrita.
MIN_TRAJECTORY_CHARS = 200

WELCOME = (
    "¡Hola! Soy tu asistente para postular a vacantes. Para empezar necesito conocer tu "
    "trayectoria. Envíame tu hoja de vida en PDF, Word o una foto, o escríbeme tu experiencia, "
    "estudios y cursos en un mensaje."
)
READING = "Recibí tu hoja de vida. La estoy leyendo, dame un momento."
UNSUPPORTED = "No pude usar ese archivo. Envíame tu hoja de vida en PDF, Word (.docx) o como foto."
REFUSED = (
    "No pude procesar ese contenido. ¿Puedes enviarlo de nuevo, o escribirme tu experiencia "
    "en un mensaje?"
)
PROFILE_READY = (
    "¡Listo! Ya tengo tu perfil. Revísalo, corrige lo que haga falta y confírmalo aquí "
    "(el enlace se puede usar una vez y vence en {hours} horas):\n{link}"
)
REVIEW_LINK = (
    "Aquí puedes revisar y ajustar tu perfil (se puede usar una vez y vence en {hours} "
    "horas):\n{link}"
)
PROFILE_CONFIRMED = (
    "¡Perfil confirmado! Muy pronto podrás enviarme vacantes para adaptar tu hoja de vida. "
    "Si quieres revisarlo otra vez, escribe *perfil*."
)
REVIEW_KEYWORDS = {"perfil", "ver perfil", "revisar", "revisar perfil", "mi perfil"}
ASK_MEDIA = {"document", "image"}


@dataclass
class Deps:
    whatsapp: WhatsAppClient
    ai: ProfileAI
    settings: Settings


def reply(session: Session, user: User, deps: Deps, text: str) -> None:
    wa_id = deps.whatsapp.send_text(user.phone, text)
    session.add(
        Message(user_id=user.id, wa_message_id=wa_id, direction="out", kind="text", body=text)
    )
    session.flush()


def record_usage(session: Session, user: User, purpose: str, result: AIResult) -> None:
    session.add(
        LlmUsage(
            user_id=user.id,
            purpose=purpose,
            model=result.model,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            request_id=result.request_id,
        )
    )


def summarize(profile: ProfileData) -> str:
    lines = ["Esto es lo que entendí de tu trayectoria:"]
    if profile.full_name:
        lines.append(f"• Nombre: {profile.full_name}")
    for exp in profile.experiences[:6]:
        period = " - ".join(x for x in (exp.start, "actual" if exp.current else exp.end) if x)
        lines.append(f"• {exp.role} en {exp.company}" + (f" ({period})" if period else ""))
    if len(profile.experiences) > 6:
        lines.append(f"• y {len(profile.experiences) - 6} experiencias más")
    if profile.education:
        lines.append(f"• Estudios: {len(profile.education)}")
    if profile.courses:
        lines.append(f"• Cursos y certificaciones: {len(profile.courses)}")
    if profile.skills:
        lines.append("• Habilidades: " + ", ".join(profile.skills[:8]))
    return "\n".join(lines)


def review_text(session: Session, user: User, deps: Deps, template: str) -> str:
    link = create_review_link(session, deps.settings, user)
    return template.format(link=link, hours=deps.settings.review_link_hours)


def next_step_text(session: Session, user: User, deps: Deps, questions: list[str]) -> str:
    if not questions:
        return review_text(session, user, deps, PROFILE_READY)
    extra = f" (me quedan {len(questions) - 1} más)" if len(questions) > 1 else ""
    return f"Para completar tu perfil necesito algunos datos{extra}.\n\n{questions[0]}"


def save_profile(session: Session, user: User, result: AIResult, existing: Profile | None) -> None:
    data = result.update.profile.model_dump()
    if existing is None:
        session.add(Profile(user_id=user.id, data=data, pending_questions=result.update.questions))
    else:
        existing.data = data
        existing.pending_questions = result.update.questions
        existing.status = "draft"
    session.flush()


def build_from_source(
    session: Session, user: User, deps: Deps, source: SourceDocument, profile: Profile | None
) -> None:
    current = ProfileData.model_validate(profile.data) if profile else None
    try:
        result = deps.ai.extract(source, current)
    except AIRefusalError:
        reply(session, user, deps, REFUSED)
        return
    record_usage(session, user, "extract_profile", result)
    save_profile(session, user, result, profile)
    reply(session, user, deps, summarize(result.update.profile))
    reply(session, user, deps, next_step_text(session, user, deps, result.update.questions))


def handle_media(
    session: Session, user: User, deps: Deps, msg: Message, profile: Profile | None
) -> None:
    media_info = msg.raw.get(msg.kind) or {}
    try:
        media = deps.whatsapp.download_media(media_info["id"])
        source = to_source(media.content, media.mime_type or media_info.get("mime_type", ""))
    except UnsupportedFileError:
        reply(session, user, deps, UNSUPPORTED)
        return
    session.add(
        StoredFile(
            user_id=user.id,
            purpose="cv_reference",
            filename=media_info.get("filename"),
            mime_type=media.mime_type,
            content=media.content,
            wa_media_id=media_info["id"],
        )
    )
    reply(session, user, deps, READING)
    build_from_source(session, user, deps, source, profile)


def handle_text(
    session: Session, user: User, deps: Deps, text: str, profile: Profile | None
) -> None:
    if profile is None:
        if len(text) >= MIN_TRAJECTORY_CHARS:
            source = SourceDocument(mime_type="text/plain", text=text)
            build_from_source(session, user, deps, source, None)
        else:
            reply(session, user, deps, WELCOME)
        return

    if text.lower().strip(" .!¡¿?") in REVIEW_KEYWORDS:
        reply(session, user, deps, review_text(session, user, deps, REVIEW_LINK))
        return

    if not profile.pending_questions:
        if profile.status == "confirmed":
            reply(session, user, deps, PROFILE_CONFIRMED)
        else:
            reply(session, user, deps, review_text(session, user, deps, REVIEW_LINK))
        return

    question = profile.pending_questions[0]
    current = ProfileData.model_validate(profile.data)
    try:
        result = deps.ai.apply_answer(current, question, text)
    except AIRefusalError:
        reply(session, user, deps, REFUSED)
        return
    record_usage(session, user, "apply_answer", result)
    save_profile(session, user, result, profile)
    reply(session, user, deps, next_step_text(session, user, deps, result.update.questions))


def handle_message(session: Session, user: User, deps: Deps, wa_message_id: str) -> None:
    msg = session.scalar(select(Message).where(Message.wa_message_id == wa_message_id))
    if msg is None:
        log.warning("Mensaje %s no encontrado", wa_message_id)
        return
    profile = session.scalar(select(Profile).where(Profile.user_id == user.id))
    if msg.kind in ASK_MEDIA:
        handle_media(session, user, deps, msg, profile)
    elif msg.kind == "text" and msg.body:
        handle_text(session, user, deps, msg.body.strip(), profile)
    else:
        reply(session, user, deps, WELCOME if profile is None else UNSUPPORTED)


def handle_profile_confirmed(session: Session, user: User, deps: Deps) -> None:
    reply(session, user, deps, PROFILE_CONFIRMED)
