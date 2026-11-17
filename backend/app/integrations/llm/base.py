"""Provider-neutral LLM interface.

Domain code depends only on this module. Concrete providers (Gemini now; OpenAI-compatible
later) live next to it. Tests inject a scripted fake that implements the same Protocol. That
fake exists only in the test suite and can't be selected at runtime (ADR-008).
"""

from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel


class LLMError(Exception):
    """Base class. Carries no prompt content, so it is safe to log."""


class LLMUnavailableError(LLMError):
    """Provider not configured, unreachable, rate-limited or timed out (after retries)."""


class LLMResponseError(LLMError):
    """Provider answered, but the output is not valid JSON or doesn't match the schema."""

    def __init__(self, message: str, raw_text: str | None = None) -> None:
        super().__init__(message)
        self.raw_text = raw_text


@dataclass(frozen=True)
class LLMUsage:
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int
    model: str


@dataclass(frozen=True)
class StructuredResult[T: BaseModel]:
    value: T
    raw_text: str
    usage: LLMUsage


class LLMProvider(Protocol):
    @property
    def model(self) -> str: ...

    def generate_structured[T: BaseModel](
        self, prompt: str, schema: type[T]
    ) -> StructuredResult[T]: ...


# ---------------------------------------------------------------- tool calling (agent)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, object]  # JSON Schema of the arguments


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    name: str
    arguments: dict[str, object]


@dataclass(frozen=True)
class AssistantTurn:
    """One model response. `raw` is provider-specific and must be replayed unchanged."""

    text: str | None
    tool_calls: list[ToolCall]
    raw: list[dict[str, object]]
    usage: LLMUsage


# Provider-neutral conversation items (all JSON-serialisable, so they can be checkpointed):
#   {"role": "user", "text": str}
#   {"role": "assistant", "text": str | None, "tool_calls": [...], "raw": [...]}
#   {"role": "tool", "call_id": str, "name": str, "result": dict}
ChatItem = dict[str, object]


class ToolCallingLLM(Protocol):
    @property
    def model(self) -> str: ...

    def chat(
        self, system: str, history: list[ChatItem], tools: list[ToolSpec]
    ) -> AssistantTurn: ...
