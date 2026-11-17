"""Embedding model interface plus the per-model settings we rely on.

Queries and documents are encoded differently on purpose: asymmetric retrieval models (bge)
are trained with an instruction prefix on the *query* side only.
"""

from dataclasses import dataclass
from typing import Protocol

import numpy as np
import numpy.typing as npt

Vector = npt.NDArray[np.float32]


@dataclass(frozen=True)
class ModelSpec:
    name: str
    dimension: int
    query_prefix: str = ""
    document_prefix: str = ""


# The model card for bge-*-v1.5 recommends this instruction for short-query -> passage search.
# Its sentence-transformers config ships with an empty prompt (verified 2026-11-17), so we
# set it here explicitly instead of relying on the config.
KNOWN_MODELS: dict[str, ModelSpec] = {
    "BAAI/bge-small-en-v1.5": ModelSpec(
        "BAAI/bge-small-en-v1.5",
        384,
        query_prefix="Represent this sentence for searching relevant passages: ",
    ),
    "sentence-transformers/all-MiniLM-L6-v2": ModelSpec(
        "sentence-transformers/all-MiniLM-L6-v2", 384
    ),
}


class Embedder(Protocol):
    @property
    def spec(self) -> ModelSpec: ...

    def encode_queries(self, texts: list[str]) -> Vector: ...

    def encode_documents(self, texts: list[str], batch_size: int = 64) -> Vector: ...
