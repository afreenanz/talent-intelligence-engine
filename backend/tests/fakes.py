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


class HashingEmbedder:
    """Deterministic bag-of-words embedder for tests: identical words -> overlapping vectors.

    It has no semantic knowledge at all; tests that need real semantics use the real model
    (marked `model`). This keeps SQL, fusion and indexing tests fast and exact.
    """

    def __init__(self, name: str = "test/hashing-384") -> None:
        from app.integrations.embeddings.base import ModelSpec

        self._spec = ModelSpec(name, 384)
        self.calls = 0

    @property
    def spec(self):  # type: ignore[no-untyped-def]
        return self._spec

    def _vec(self, text: str):  # type: ignore[no-untyped-def]
        import hashlib
        import re

        import numpy as np

        v = np.zeros(384, dtype=np.float32)
        for tok in re.findall(r"[a-z0-9+#]+", text.lower()):
            v[int(hashlib.md5(tok.encode()).hexdigest(), 16) % 384] += 1.0  # noqa: S324
        n = float(np.linalg.norm(v))
        return v / n if n else v

    def encode_queries(self, texts):  # type: ignore[no-untyped-def]
        import numpy as np

        self.calls += len(texts)
        return np.stack([self._vec(t) for t in texts])

    def encode_documents(self, texts, batch_size=64):  # type: ignore[no-untyped-def]
        return self.encode_queries(texts)


class KeywordReranker:
    """Test-only cross-encoder stand-in: score = number of query words present in the document."""

    name = "test/keyword-reranker"

    def __init__(self) -> None:
        self.calls: list[int] = []

    def score(self, pairs: list[tuple[str, str]]) -> list[float]:
        self.calls.append(len(pairs))
        return [float(sum(w in d.lower() for w in q.lower().split())) for q, d in pairs]


class ScriptedToolLLM:
    """Test-only tool-calling LLM. Each script entry is a function(history) -> AssistantTurn,
    so a turn can depend on earlier tool results (e.g. cite a job_id that search returned)."""

    def __init__(self, *script):  # type: ignore[no-untyped-def]
        self.script = list(script)
        self.calls: list[list[dict]] = []  # type: ignore[type-arg]

    @property
    def model(self) -> str:
        return "scripted-tool-llm"

    def chat(self, system, history, tools):  # type: ignore[no-untyped-def]
        self.calls.append([dict(h) for h in history])
        self.system = system
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step(history)


def tool_turn(*calls):  # type: ignore[no-untyped-def]
    """Assistant turn requesting tool calls: tool_turn(("search_jobs", {...}), ...)."""
    from app.integrations.llm.base import AssistantTurn, LLMUsage, ToolCall

    def make(history):  # type: ignore[no-untyped-def]
        resolved = [(n, a(history) if callable(a) else a) for n, a in calls]
        return AssistantTurn(
            text=None,
            tool_calls=[
                ToolCall(f"call_{len(history)}_{i}", n, a) for i, (n, a) in enumerate(resolved)
            ],
            raw=[
                {
                    "type": "function_call",
                    "id": f"call_{len(history)}_{i}",
                    "name": n,
                    "arguments": a,
                }
                for i, (n, a) in enumerate(resolved)
            ],
            usage=LLMUsage(10, 5, 1, "scripted"),
        )

    return make


def text_turn(text):  # type: ignore[no-untyped-def]
    """Final assistant text; `text` may be a function(history) -> str."""
    from app.integrations.llm.base import AssistantTurn, LLMUsage

    def make(history):  # type: ignore[no-untyped-def]
        t = text(history) if callable(text) else text
        return AssistantTurn(
            text=t,
            tool_calls=[],
            raw=[{"type": "model_output", "content": [{"type": "text", "text": t}]}],
            usage=LLMUsage(10, 5, 1, "scripted"),
        )

    return make


def last_tool_result(history, name):  # type: ignore[no-untyped-def]
    return next(
        h["result"] for h in reversed(history) if h.get("role") == "tool" and h["name"] == name
    )
