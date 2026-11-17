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
