"""Stage 2: cross-encoder re-ranking of the top-N stage-1 results.

A cross-encoder reads (query, document) *together*, so it can model interactions a bi-encoder
can't, at the cost of one forward pass per pair (~6 ms/pair on this laptop's CPU; 50 pairs ≈ 0.3 s).
Model: cross-encoder/ms-marco-MiniLM-L6-v2 (ADR-007). It is trained on web passages, not jobs,
so whether it helps here is measured in Milestone 4B, not assumed.

Normalisation (decided from a live run, 2026-11-17): the model's logits are mapped through its
own calibrated sigmoid before blending. A first version min-max-normalised logits *within* each
result list. On near-identical synthetic postings the logits spanned only 6.37-6.62, and
min-max stretched that noise to the full [0, 1] range, letting the cross-encoder override real
signals (all top-5 results ended up in the wrong city). Sigmoid keeps "can't tell them apart"
as a near-zero effect.
"""

import math
from functools import lru_cache
from typing import Protocol

CROSS_ENCODER_MODEL = "cross-encoder/ms-marco-MiniLM-L6-v2"


class Reranker(Protocol):
    @property
    def name(self) -> str: ...

    def score(self, pairs: list[tuple[str, str]]) -> list[float]: ...


class SentenceTransformerCrossEncoder:
    def __init__(self, model: str = CROSS_ENCODER_MODEL, device: str = "cpu") -> None:
        from sentence_transformers import CrossEncoder  # heavy import, deferred

        self._name = model
        self._model = CrossEncoder(model, device=device)

    @property
    def name(self) -> str:
        return self._name

    def score(self, pairs: list[tuple[str, str]]) -> list[float]:
        if not pairs:
            return []
        logits = self._model.predict(pairs, batch_size=32, show_progress_bar=False)
        return [float(x) for x in logits]


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x)) if x >= 0 else math.exp(x) / (1.0 + math.exp(x))


def min_max(values: list[float]) -> list[float]:
    """Kept for analysis and tests; not used for blending (see module docstring)."""
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi - lo < 1e-9:
        return [0.5] * len(values)  # no information to separate them
    return [(v - lo) / (hi - lo) for v in values]


@lru_cache
def get_cross_encoder() -> SentenceTransformerCrossEncoder:
    return SentenceTransformerCrossEncoder()
