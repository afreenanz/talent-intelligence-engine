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
