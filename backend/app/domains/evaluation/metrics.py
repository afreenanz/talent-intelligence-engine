"""Ranking metrics. Pure functions over (ranked ids, graded relevance judgments).

Conventions (documented so the numbers mean one thing):
- Judgments are graded 0-3. Binary metrics (P, R, MRR) treat grade >= RELEVANT_GRADE as relevant.
- Documents with no judgment are non-relevant (standard TREC assumption).
- NDCG uses exponential gain (2^g - 1) and log2(rank + 1) discount; IDCG is computed from
  *all* judged documents, not just the retrieved ones. Otherwise a system that retrieves
  nothing relevant could still score 1.0.
- Recall@K and NDCG@K are undefined for a query with no relevant documents. Callers must
  exclude such queries; `validate_judgments` enforces this for datasets.
"""

import math
from collections.abc import Hashable, Mapping, Sequence

RELEVANT_GRADE = 2


def _relevant[K: Hashable](j: Mapping[K, int]) -> set[K]:
    return {d for d, g in j.items() if g >= RELEVANT_GRADE}


def precision_at_k[K: Hashable](ranked: Sequence[K], judgments: Mapping[K, int], k: int) -> float:
    if k <= 0:
        raise ValueError("k must be positive")
    rel = _relevant(judgments)
    return sum(1 for d in ranked[:k] if d in rel) / k


def recall_at_k[K: Hashable](ranked: Sequence[K], judgments: Mapping[K, int], k: int) -> float:
    rel = _relevant(judgments)
    if not rel:
        raise ValueError("recall is undefined for a query with no relevant documents")
    return sum(1 for d in ranked[:k] if d in rel) / len(rel)


def reciprocal_rank[K: Hashable](
    ranked: Sequence[K], judgments: Mapping[K, int], k: int | None = None
) -> float:
    rel = _relevant(judgments)
    for i, d in enumerate(ranked[:k] if k else ranked, start=1):
        if d in rel:
            return 1.0 / i
    return 0.0


def average_precision[K: Hashable](
    ranked: Sequence[K], judgments: Mapping[K, int], k: int | None = None
) -> float:
    """AP: mean of P@i over the ranks i of relevant hits, divided by *all* relevant documents
    (unretrieved relevant documents count as zero precision). MAP = mean AP over queries."""
    rel = _relevant(judgments)
    if not rel:
        raise ValueError("AP is undefined for a query with no relevant documents")
    hits, total = 0, 0.0
    for i, d in enumerate(ranked[:k] if k else ranked, start=1):
        if d in rel:
            hits += 1
            total += hits / i
    return total / len(rel)


def dcg_at_k(gains: Sequence[int], k: int) -> float:
    return math.fsum((2**g - 1) / math.log2(i + 1) for i, g in enumerate(gains[:k], start=1))


def ndcg_at_k[K: Hashable](ranked: Sequence[K], judgments: Mapping[K, int], k: int) -> float:
    ideal = sorted((g for g in judgments.values() if g > 0), reverse=True)
    idcg = dcg_at_k(ideal, k)
    if idcg == 0:
        raise ValueError("NDCG is undefined for a query with no relevant documents")
    return dcg_at_k([judgments.get(d, 0) for d in ranked], k) / idcg


def validate_judgments[K: Hashable](qrels: Mapping[str, Mapping[K, int]]) -> list[str]:
    """Return a list of problems; empty means the dataset is usable."""
    problems = []
    for qid, j in qrels.items():
        if not _relevant(j):
            problems.append(f"{qid}: no document with grade >= {RELEVANT_GRADE}")
        bad = [g for g in j.values() if not 0 <= g <= 3]
        if bad:
            problems.append(f"{qid}: grades out of range {bad[:3]}")
    return problems
