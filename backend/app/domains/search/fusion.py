"""Reciprocal Rank Fusion (Cormack, Clarke & Büttcher, SIGIR 2009).

    fused(d) = Σ_r  w_r / (k + rank_r(d))      rank is 1-based; absent from list r -> 0

Why rank-based fusion: lexical scores (ts_rank_cd) and cosine similarities live on different,
uncalibrated scales. Adding them would let whichever happens to have larger numbers dominate.
Ranks are comparable across retrievers without any calibration.
k (default 60) damps the advantage of the very top ranks: with k=60, rank 1 vs rank 2 differ by
only ~1.6%, so a document ranked well by *both* retrievers beats one ranked first by only one.
"""

import uuid
from collections.abc import Mapping, Sequence


def reciprocal_rank_fusion(
    ranked_lists: Mapping[str, Sequence[uuid.UUID]],
    *,
    k: int = 60,
    weights: Mapping[str, float] | None = None,
) -> list[tuple[uuid.UUID, float]]:
    if k <= 0:
        raise ValueError("k must be positive")
    scores: dict[uuid.UUID, float] = {}
    for name, ids in ranked_lists.items():
        w = (weights or {}).get(name, 1.0)
        for rank, doc_id in enumerate(ids, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + w / (k + rank)
    # Ties broken by id so the output is fully deterministic.
    return sorted(scores.items(), key=lambda kv: (-kv[1], str(kv[0])))
