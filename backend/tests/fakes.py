"""Test-only LLM fake. It implements the LLMProvider protocol and is never importable from app/."""

from pydantic import BaseModel

from app.integrations.llm.base import LLMUsage, StructuredResult


class ScriptedLLM:
    """Returns pre-scripted results in order; an Exception in the script is raised instead."""

    def __init__(self, *script: BaseModel | Exception) -> None:
        self.script = list(script)
        self.prompts: list[str] = []

    @property
    def model(self) -> str:
        return "scripted-fake"

    def generate_structured[T: BaseModel](
        self, prompt: str, schema: type[T]
    ) -> StructuredResult[T]:
        self.prompts.append(prompt)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        value = schema.model_validate(item.model_dump())
        return StructuredResult(
            value=value,
            raw_text=item.model_dump_json(),
            usage=LLMUsage(input_tokens=100, output_tokens=50, latency_ms=5, model=self.model),
        )
