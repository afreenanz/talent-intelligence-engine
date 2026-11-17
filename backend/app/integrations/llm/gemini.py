"""Gemini adapter over the REST Interactions API.

Why REST via httpx rather than the google-genai SDK: during Milestone 2B the docs and SDK were
mid-transition (`generate_content` returned 404 for the current free-tier models, while the
documented path is the newer Interactions API). A ~100-line adapter over the documented REST
contract is easier to verify, test with a mock transport, and pin with an API revision header.

Response shape, verified live on 2026-11-17 against gemini-3.5-flash-lite:
    {"status": "completed",
     "steps": [{"type": "thought", ...}, {"type": "model_output",
                                           "content": [{"type": "text", "text": "{...}"}]}],
     "usage": {"total_input_tokens": 26, "total_output_tokens": 40, ...}}
"""

import json
import time
from typing import Any

import httpx
import structlog
from pydantic import BaseModel, ValidationError

from app.integrations.llm.base import (
    AssistantTurn,
    ChatItem,
    LLMResponseError,
    LLMUnavailableError,
    LLMUsage,
    StructuredResult,
    ToolCall,
    ToolSpec,
)

log = structlog.get_logger(__name__)

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class GeminiProvider:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        api_revision: str,
        timeout_seconds: float,
        max_retries: int,
        transport: httpx.BaseTransport | None = None,
        sleep: Any = time.sleep,
    ) -> None:
        self._model = model
        self._max_retries = max_retries
        self._sleep = sleep
        self._client = httpx.Client(
            base_url=base_url,
            timeout=httpx.Timeout(timeout_seconds, connect=10.0),
            headers={
                # Header, never a URL query param: keeps the key out of access logs.
                "x-goog-api-key": api_key,
                "Content-Type": "application/json",
                "Api-Revision": api_revision,
            },
            transport=transport,
        )

    @property
    def model(self) -> str:
        return self._model

    def generate_structured[T: BaseModel](
        self, prompt: str, schema: type[T]
    ) -> StructuredResult[T]:
        body = {
            "model": self._model,
            "input": prompt,
            "response_format": {
                "type": "text",
                "mime_type": "application/json",
                "schema": _provider_schema(schema),
            },
        }
        started = time.perf_counter()
        data = self._post_with_retries(body)
        latency_ms = int((time.perf_counter() - started) * 1000)

        text = _extract_output_text(data)
        try:
            value = schema.model_validate_json(text)
        except ValidationError as exc:
            # Constraints such as maxLength are not enforced by the provider (per its docs),
            # so application-side validation is the real gate.
            raise LLMResponseError(
                f"output does not match schema: {exc.error_count()} errors", raw_text=text
            ) from exc
        usage = data.get("usage") or {}
        return StructuredResult(
            value=value,
            raw_text=text,
            usage=LLMUsage(
                input_tokens=usage.get("total_input_tokens"),
                output_tokens=usage.get("total_output_tokens"),
                latency_ms=latency_ms,
                model=str(data.get("model") or self._model),
            ),
        )

    def chat(self, system: str, history: list[ChatItem], tools: list[ToolSpec]) -> AssistantTurn:
        """Stateless tool-calling turn (store=false: Google keeps no conversation state).

        Verified live (2026-11-18): the input is the full ordered history, model steps (including
        `thought` steps with signatures) replayed unchanged, and tool results sent as
        `function_result` steps. Several function calls can come back in one response.
        """
        body = {
            "model": self._model,
            "store": False,
            "system_instruction": system,
            "input": [step for item in history for step in _to_steps(item)],
            "tools": [
                {
                    "type": "function",
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                }
                for t in tools
            ],
        }
        started = time.perf_counter()
        data = self._post_with_retries(body)
        latency_ms = int((time.perf_counter() - started) * 1000)
        if data.get("status") not in (None, "completed", "requires_action"):
            raise LLMUnavailableError(f"LLM interaction not completed: {data.get('status')}")
        steps: list[dict[str, Any]] = list(data.get("steps") or [])
        calls = [
            ToolCall(
                call_id=str(st["id"]),
                name=str(st["name"]),
                arguments=dict(st.get("arguments") or {}),
            )
            for st in steps
            if st.get("type") == "function_call"
        ]
        text = (
            "".join(
                part.get("text", "")
                for st in steps
                if st.get("type") == "model_output"
                for part in st.get("content") or []
                if part.get("type") == "text"
            ).strip()
            or None
        )
        if not calls and not text:
            raise LLMResponseError("LLM returned neither text nor tool calls")
        usage = data.get("usage") or {}
        return AssistantTurn(
            text=text,
            tool_calls=calls,
            raw=steps,
            usage=LLMUsage(
                usage.get("total_input_tokens"),
                usage.get("total_output_tokens"),
                latency_ms,
                str(data.get("model") or self._model),
            ),
        )

    def _post_with_retries(self, body: dict[str, Any]) -> dict[str, Any]:
        attempt = 0
        while True:
            try:
                response = self._client.post("/interactions", json=body)
            except httpx.TimeoutException as exc:
                error: Exception = LLMUnavailableError("LLM request timed out")
                error.__cause__ = exc
            except httpx.TransportError as exc:
                error = LLMUnavailableError(f"LLM transport error: {type(exc).__name__}")
                error.__cause__ = exc
            else:
                if response.status_code == 200:
                    payload: dict[str, Any] = response.json()
                    return payload
                if response.status_code not in _RETRYABLE_STATUS:
                    # 4xx other than 429: our request is wrong. Retrying won't help.
                    raise LLMResponseError(
                        f"LLM request rejected: HTTP {response.status_code} "
                        f"{_error_status(response)}"
                    )
                error = LLMUnavailableError(
                    f"LLM unavailable: HTTP {response.status_code} {_error_status(response)}"
                )

            if attempt >= self._max_retries:
                raise error
            delay = 2.0**attempt  # 1s, 2s, 4s
            log.warning("llm_retry", attempt=attempt + 1, delay_s=delay, reason=str(error))
            self._sleep(delay)
            attempt += 1


def _to_steps(item: ChatItem) -> list[dict[str, Any]]:
    role = item["role"]
    if role == "user":
        return [{"type": "user_input", "content": [{"type": "text", "text": item["text"]}]}]
    if role == "assistant":
        raw = item.get("raw")
        return list(raw) if isinstance(raw, list) else []
    if role == "tool":
        return [
            {
                "type": "function_result",
                "name": item["name"],
                "call_id": item["call_id"],
                "result": [{"type": "text", "text": json.dumps(item["result"], default=str)}],
            }
        ]
    raise ValueError(f"unknown chat item role {role!r}")


def _extract_output_text(data: dict[str, Any]) -> str:
    if data.get("status") not in (None, "completed"):
        raise LLMUnavailableError(f"LLM interaction not completed: {data.get('status')}")
    texts = [
        part.get("text", "")
        for step in data.get("steps") or []
        if step.get("type") == "model_output"
        for part in step.get("content") or []
        if part.get("type") == "text"
    ]
    text = "".join(texts).strip()
    if not text:
        raise LLMResponseError("LLM returned no model_output text")
    try:
        json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMResponseError("LLM output is not valid JSON", raw_text=text) from exc
    return text


def _error_status(response: httpx.Response) -> str:
    try:
        return str(response.json().get("error", {}).get("status") or "")
    except ValueError:
        return ""


def _provider_schema(schema: type[BaseModel]) -> dict[str, Any]:
    """Pydantic JSON schema adapted to the provider's supported subset.

    - `$ref`/`$defs` are inlined (nested $ref support varies).
    - `anyOf: [{type: X}, {type: null}]` becomes `type: [X, "null"]`; the docs recommend fewer
      anyOf branches, and this form was verified live.
    - Pydantic's `title` *metadata* is dropped, but a *property named* "title" is kept
      (a first version dropped both and the API rejected the schema).
    """
    raw = schema.model_json_schema()
    defs = raw.pop("$defs", {})

    def resolve(node: Any, *, is_properties_map: bool = False) -> Any:
        if isinstance(node, list):
            return [resolve(v) for v in node]
        if not isinstance(node, dict):
            return node
        if is_properties_map:  # keys are field names, values are schemas
            return {name: resolve(sub) for name, sub in node.items()}
        if "$ref" in node:
            return resolve(defs[node["$ref"].split("/")[-1]])
        branches = node.get("anyOf")
        if isinstance(branches, list) and len(branches) == 2 and {"type": "null"} in branches:
            other = resolve(next(b for b in branches if b != {"type": "null"}))
            if isinstance(other.get("type"), str):
                merged = {**{k: v for k, v in node.items() if k not in ("anyOf", "title")}, **other}
                merged["type"] = [other["type"], "null"]
                merged.pop("default", None)
                return merged
        out: dict[str, Any] = {}
        for key, value in node.items():
            if key in ("title", "default"):
                continue
            out[key] = resolve(value, is_properties_map=(key == "properties"))
        return out

    resolved: dict[str, Any] = resolve(raw)
    return resolved
