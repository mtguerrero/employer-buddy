from types import SimpleNamespace

import pytest

from employer_buddy.ai import AIRefusalError, ClaudeProfileAI, SourceDocument
from employer_buddy.profile_schema import ProfileUpdate
from tests.fakes import sample_profile


class StubClient:
    def __init__(self, response):
        self.kwargs = None
        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=self._parse))
        self._response = response

    def _parse(self, **kwargs):
        self.kwargs = kwargs
        return self._response


def response(parsed, stop_reason="end_turn"):
    return SimpleNamespace(
        parsed_output=parsed,
        stop_reason=stop_reason,
        stop_details=None,
        model="claude-opus-5-5",
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
        _request_id="req_1",
    )


def test_pdf_va_como_documento_con_fallback(settings):
    update = ProfileUpdate(profile=sample_profile(), questions=["¿Qué cargo buscas?"])
    stub = StubClient(response(update))
    result = ClaudeProfileAI(settings, client=stub).extract(
        SourceDocument(mime_type="application/pdf", content=b"%PDF"), None
    )

    assert result.update == update and result.input_tokens == 10
    kw = stub.kwargs
    assert kw["model"] == "claude-opus-5-5"
    assert kw["output_format"] is ProfileUpdate
    assert kw["fallbacks"] == "default"
    assert kw["betas"] == ["server-side-fallback-2026-07-01"]
    first = kw["messages"][0]["content"][0]
    assert first["type"] == "document" and first["source"]["media_type"] == "application/pdf"


def test_rechazo_lanza_error(settings):
    stub = StubClient(response(None, stop_reason="refusal"))
    with pytest.raises(AIRefusalError):
        ClaudeProfileAI(settings, client=stub).apply_answer(sample_profile(), "¿?", "x")


def test_si_el_esquema_es_muy_grande_pide_json_por_instrucciones(settings):
    import anthropic
    import httpx

    update = ProfileUpdate(profile=sample_profile(), questions=["¿Nivel de inglés?"])
    stub = StubClient(None)

    def parse(**kwargs):
        request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        raise anthropic.BadRequestError(
            "The compiled grammar is too large",
            response=httpx.Response(400, request=request),
            body=None,
        )

    def create(**kwargs):
        stub.kwargs = kwargs
        text = "```json\n" + update.model_dump_json() + "\n```"
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=text)],
            stop_reason="end_turn",
            stop_details=None,
            model="claude-opus-5-5",
            usage=SimpleNamespace(input_tokens=20, output_tokens=8),
            _request_id="req_2",
        )

    stub.beta = SimpleNamespace(messages=SimpleNamespace(parse=parse, create=create))
    result = ClaudeProfileAI(settings, client=stub).extract(
        SourceDocument(mime_type="text/plain", text="CV"), None
    )

    assert result.update == update
    assert "output_format" not in stub.kwargs
    assert stub.kwargs["fallbacks"] == "default"
    assert "esquema JSON" in stub.kwargs["messages"][0]["content"][-1]["text"]
