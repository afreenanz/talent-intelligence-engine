"""Gemini adapter against a mock HTTP transport. No network calls."""

import json
from typing import Any

import httpx
import pytest
from pydantic import BaseModel

from app.integrations.llm.base import LLMResponseError, LLMUnavailableError
from app.integrations.llm.gemini import GeminiProvider, _provider_schema


class Out(BaseModel):
    name: str | None
    skills: list[str]


def ok_body(text: str) -> dict[str, Any]:
    return {
        "status": "completed",
        "model": "gemini-test",
        "steps": [
            {"type": "thought", "signature": "x"},
            {"type": "model_output", "content": [{"type": "text", "text": text}]},
        ],
        "usage": {"total_input_tokens": 26, "total_output_tokens": 40},
    }


def make(
    responses: list[httpx.Response | Exception], **kw: Any
) -> tuple[GeminiProvider, list[httpx.Request], list[float]]:
    seen: list[httpx.Request] = []
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        item = responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    provider = GeminiProvider(
        api_key="test-key",
        model="gemini-test",
        base_url="https://example.test/v1beta",
        api_revision="2026-05-20",
        timeout_seconds=5,
        max_retries=kw.get("max_retries", 2),
        transport=httpx.MockTransport(handler),
        sleep=sleeps.append,
    )
    return provider, seen, sleeps


def test_success_parses_model_output_and_usage() -> None:
    p, seen, _ = make([httpx.Response(200, json=ok_body('{"name": "Jane", "skills": ["Python"]}'))])
    result = p.generate_structured("prompt", Out)
    assert result.value == Out(name="Jane", skills=["Python"])
    assert (result.usage.input_tokens, result.usage.output_tokens) == (26, 40)

    req = seen[0]
    assert req.url.path.endswith("/interactions")
    assert req.headers["x-goog-api-key"] == "test-key" and "key=" not in str(req.url)
    assert req.headers["api-revision"] == "2026-05-20"
    body = json.loads(req.content)
    assert body["response_format"]["mime_type"] == "application/json"


def test_retries_on_429_then_succeeds_with_backoff() -> None:
    p, seen, sleeps = make(
        [
            httpx.Response(429, json={"error": {"status": "RESOURCE_EXHAUSTED"}}),
            httpx.Response(503),
            httpx.Response(200, json=ok_body('{"name": null, "skills": []}')),
        ]
    )
    assert p.generate_structured("x", Out).value.skills == []
    assert len(seen) == 3 and sleeps == [1.0, 2.0]


def test_gives_up_after_max_retries() -> None:
    p, seen, _ = make([httpx.Response(503)] * 3)
    with pytest.raises(LLMUnavailableError, match="503"):
        p.generate_structured("x", Out)
    assert len(seen) == 3


def test_timeout_is_unavailable() -> None:
    p, _, _ = make([httpx.ReadTimeout("slow")], max_retries=0)
    with pytest.raises(LLMUnavailableError, match="timed out"):
        p.generate_structured("x", Out)


def test_client_errors_are_not_retried() -> None:
    p, seen, _ = make([httpx.Response(400, json={"error": {"status": "invalid_request"}})])
    with pytest.raises(LLMResponseError, match="400"):
        p.generate_structured("x", Out)
    assert len(seen) == 1


@pytest.mark.parametrize(
    ("text", "match"),
    [
        ("not json", "not valid JSON"),
        ('{"name": 5}', "does not match schema"),
        ("", "no model_output"),
    ],
)
def test_bad_output_raises_response_error(text: str, match: str) -> None:
    p, _, _ = make([httpx.Response(200, json=ok_body(text))])
    with pytest.raises(LLMResponseError, match=match):
        p.generate_structured("x", Out)


def test_schema_conversion_keeps_fields_named_title_and_flattens_nullables() -> None:
    class Work(BaseModel):
        title: str | None
        company: str

    class Root(BaseModel):
        jobs: list[Work]

    schema = _provider_schema(Root)
    item = schema["properties"]["jobs"]["items"]
    assert set(item["properties"]) == {"title", "company"}  # regression: "title" was stripped
    assert item["properties"]["title"]["type"] == ["string", "null"]
    assert "$defs" not in schema and "title" not in schema
