"""Llamadas a Claude para construir y completar el perfil maestro."""

import base64
import json
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol

import anthropic

from employer_buddy.config import Settings
from employer_buddy.profile_schema import ProfileData, ProfileUpdate, fill_education_status

RULES = """Eres el asistente que construye el perfil maestro de una persona que busca empleo.
El perfil maestro es la fuente de verdad para escribir hojas de vida después, así que:
- Registra solo hechos que aparezcan en el material o que la persona haya dicho. Nunca inventes
  cargos, fechas, cifras, habilidades ni estudios. Si un dato no aparece, déjalo vacío.
- Copia las viñetas de cada experiencia tal como están, en el mismo orden. Solo corrige errores
  de ortografía (tildes, letras faltantes). No las resumas, no las reescribas, no las dividas.
- Normaliza las fechas a AAAA-MM o AAAA.
- Estado de estudios y cursos: usa el que diga el material. Si no lo dice, un estudio con fecha
  de fin ya pasada está "Finalizado" y uno que dice "Presente" o "Actualidad" está "En curso".
- Escribe los textos en español. Los nombres propios, cargos y tecnologías se dejan como aparecen.

Preguntas para completar el perfil: máximo 7, en tono cercano, tuteando, una idea por pregunta,
solo sobre lo que de verdad falta, en este orden:
1. Preferencias de búsqueda en UNA sola pregunta: cargos que busca, ciudad o país, modalidad
   (presencial, híbrida o remota) y aspiración salarial.
2. Logros sin resultados medibles: una pregunta por experiencia, empezando por la más reciente,
   pidiendo cifras concretas de esa experiencia (personas, áreas, horas, porcentajes, dinero,
   volumen). Nombra la empresa y lo que hizo. Máximo 3 preguntas de este tipo.
3. Idiomas sin nivel.
4. Experiencias con fechas que se cruzan: pregunta si alguna fue por horas, independiente o en
   paralelo.
5. Fechas que faltan, y enlaces (LinkedIn o portafolio) si no hay ninguno."""


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


def _check_refusal(response: Any) -> None:
    if response.stop_reason == "refusal":
        raise AIRefusalError(str(response.stop_details or response.stop_reason))


def _strip_fences(text: str) -> str:
    """Quita un bloque ```json ... ``` si el modelo lo agregó."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0]
    return text.strip()


def _result(response: Any, update: ProfileUpdate) -> AIResult:
    update.profile = fill_education_status(update.profile, date.today())
    return AIResult(
        update=update,
        model=response.model,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        request_id=getattr(response, "_request_id", None),
    )


class ClaudeProfileAI:
    def __init__(self, settings: Settings, client: anthropic.Anthropic | None = None) -> None:
        self._settings = settings
        if client is None:
            # Sin clave explícita, el SDK la busca en las variables de entorno.
            key = settings.anthropic_api_key or None
            client = anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()
        self._client = client

    def _call(self, content: list[dict[str, Any]]) -> AIResult:
        common: dict[str, Any] = {
            "model": self._settings.anthropic_model,
            "max_tokens": 16000,
            "system": RULES,
            "output_config": {"effort": self._settings.anthropic_effort},
            "betas": ["server-side-fallback-2026-07-01"],
            "fallbacks": "default",
        }
        try:
            response = self._client.beta.messages.parse(
                messages=[{"role": "user", "content": content}],
                output_format=ProfileUpdate,
                **common,
            )
        except anthropic.BadRequestError as exc:
            if "grammar" not in str(exc).lower():
                raise
            # La API no pudo compilar el esquema como salida estructurada: se pide el JSON
            # por instrucciones y se valida aquí con el mismo modelo de datos.
            return self._call_with_json_instructions(content, common)
        _check_refusal(response)
        if response.parsed_output is None:
            raise AIRefusalError(str(response.stop_reason))
        return _result(response, response.parsed_output)

    def _call_with_json_instructions(
        self, content: list[dict[str, Any]], common: dict[str, Any]
    ) -> AIResult:
        schema = json.dumps(ProfileUpdate.model_json_schema(), ensure_ascii=False)
        instructions = {
            "type": "text",
            "text": "Responde solo con un objeto JSON válido, sin texto adicional ni bloques de "
            f"código, que cumpla este esquema JSON:\n{schema}",
        }
        response = self._client.beta.messages.create(
            messages=[{"role": "user", "content": [*content, instructions]}],
            **common,
        )
        _check_refusal(response)
        text = "".join(b.text for b in response.content if b.type == "text")
        return _result(response, ProfileUpdate.model_validate_json(_strip_fences(text)))

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
            "Actualiza el perfil solo con lo que dice la respuesta. Si la respuesta trae una cifra "
            "o un resultado de una experiencia, agrégalo a la viñeta a la que corresponde, "
            "cambiando lo menos posible el resto de la frase; si no corresponde a ninguna, "
            "agrégalo como viñeta nueva de esa experiencia. Si la respuesta no contesta "
            "la pregunta, deja la pregunta en la lista. Devuelve las preguntas que siguen "
            "pendientes, sin repetir las ya contestadas."
        )
        return self._call([{"type": "text", "text": text}])
