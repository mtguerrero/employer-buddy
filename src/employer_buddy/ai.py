"""Llamadas a Claude para construir y completar el perfil maestro."""

import base64
import json
from dataclasses import dataclass
from typing import Any, Protocol

import anthropic

from employer_buddy.config import Settings
from employer_buddy.profile_schema import ProfileData, ProfileUpdate

RULES = """Eres el asistente que construye el perfil maestro de una persona que busca empleo.
El perfil maestro es la fuente de verdad para escribir hojas de vida después, así que:
- Registra solo hechos que aparezcan en el material o que la persona haya dicho. Nunca inventes
  cargos, fechas, cifras, habilidades ni estudios. Si un dato no aparece, déjalo en null o vacío.
- Conserva las cifras de los logros tal como están.
- Normaliza las fechas a AAAA-MM o AAAA.
- Escribe los textos en español. Los nombres propios, cargos y tecnologías se dejan como aparecen.
- Las preguntas sirven para completar lo que falta y para que la hoja de vida sea mejor:
  fechas que faltan, logros sin resultados medibles, y las preferencias de búsqueda (cargos que
  busca, ciudad o modalidad, aspiración salarial). Pregunta solo lo que de verdad falta,
  en tono cercano, una idea por pregunta, máximo 5."""


class AIRefusalError(Exception):
    """Claude declinó la solicitud."""


@dataclass(frozen=True)
class AIResult:
    update: ProfileUpdate
    model: str
    input_tokens: int
    output_tokens: int
    request_id: str | None


@dataclass(frozen=True)
class SourceDocument:
    """Material de entrada: PDF o imagen como bytes, o texto plano."""

    mime_type: str
    content: bytes | None = None
    text: str | None = None


class ProfileAI(Protocol):
    def extract(self, source: SourceDocument, current: ProfileData | None) -> AIResult: ...

    def apply_answer(self, current: ProfileData, question: str, answer: str) -> AIResult: ...


def _source_block(source: SourceDocument) -> dict[str, Any]:
    if source.text is not None:
        return {"type": "text", "text": f"<material>\n{source.text}\n</material>"}
    assert source.content is not None
    data = base64.standard_b64encode(source.content).decode()
    if source.mime_type == "application/pdf":
        return {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": data},
        }
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": source.mime_type, "data": data},
    }


class ClaudeProfileAI:
    def __init__(self, settings: Settings, client: anthropic.Anthropic | None = None) -> None:
        self._settings = settings
        if client is None:
            # Sin clave explícita, el SDK la busca en las variables de entorno.
            key = settings.anthropic_api_key or None
            client = anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()
        self._client = client

    def _call(self, content: list[dict[str, Any]]) -> AIResult:
        response = self._client.beta.messages.parse(
            model=self._settings.anthropic_model,
            max_tokens=16000,
            system=RULES,
            messages=[{"role": "user", "content": content}],
            output_format=ProfileUpdate,
            output_config={"effort": self._settings.anthropic_effort},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if response.stop_reason == "refusal" or response.parsed_output is None:
            raise AIRefusalError(str(response.stop_details or response.stop_reason))
        return AIResult(
            update=response.parsed_output,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            request_id=getattr(response, "_request_id", None),
        )

    def extract(self, source: SourceDocument, current: ProfileData | None) -> AIResult:
        content: list[dict[str, Any]] = [_source_block(source)]
        if current is not None:
            content.append(
                {
                    "type": "text",
                    "text": "Perfil actual (consérvalo y complétalo con el material nuevo):\n"
                    + json.dumps(current.model_dump(), ensure_ascii=False),
                }
            )
        content.append(
            {
                "type": "text",
                "text": "Construye el perfil maestro con este material y lista lo que falta.",
            }
        )
        return self._call(content)

    def apply_answer(self, current: ProfileData, question: str, answer: str) -> AIResult:
        text = (
            "Perfil actual:\n"
            + json.dumps(current.model_dump(), ensure_ascii=False)
            + f"\n\nLe preguntaste: {question}\nRespondió: {answer}\n\n"
            "Actualiza el perfil solo con lo que dice la respuesta. Si la respuesta no contesta "
            "la pregunta, deja la pregunta en la lista. Devuelve las preguntas que siguen "
            "pendientes, sin repetir las ya contestadas."
        )
        return self._call([{"type": "text", "text": text}])
