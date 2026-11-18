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
