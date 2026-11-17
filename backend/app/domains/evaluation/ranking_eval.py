"""Ranking evaluation on TalentCLEF 2026 Task A (development split, English).

Every stage reuses production code: the same OR-tsquery and ts_rank_cd normalisation (via a
temporary table), the same embedding model and query prefix, the same RRF, the same features,
the same weights file, and the same cross-encoder blend. Only the data source differs.

Pipeline per job query (depth 100, like production):
  lexical / dense / hybrid  ->  stage 1 features  ->  optional cross-encoder on the top 50
Exploratory: LambdaMART (LightGBM) with leave-one-query-out cross-validation.
"""

import statistics
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from sqlalchemy import Column, MetaData, Table, Text, func, insert, select, update
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Session

from app.domains.evaluation import metrics as m
from app.domains.evaluation.models import EvaluationRun
from app.domains.evaluation.retrieval_eval import BOOTSTRAP_SAMPLES, git_commit
from app.domains.evaluation.talentclef import TCDataset
from app.domains.ranking.cross_encoder import Reranker, sigmoid
from app.domains.ranking.features import (
    FEATURE_NAMES,
    CandidateFacts,
    JobFacts,
    compute_features,
)
from app.domains.ranking.service import CROSS_ENCODER_BLEND, CROSS_ENCODER_TOP_N
from app.domains.ranking.weighted import WeightedRanker
from app.domains.search.fusion import reciprocal_rank_fusion
from app.domains.search.retrievers import LEXICAL_RANK_NORMALIZATION, or_tsquery
from app.domains.skills.extraction import _compile
from app.integrations.embeddings.base import Embedder

DEPTH = 100
NOW = datetime(
    2026, 4, 1, tzinfo=UTC
)  # recency is neutral here (no dates); fixed for reproducibility
METRICS = ("ndcg@10", "map@100", "mrr@10", "p@10", "recall@100")
RELEVANT = 3  # TalentCLEF labels are binary; mapped to our top grade (>= RELEVANT_GRADE)


@dataclass
class Candidates:
    """Everything computed once per query and shared by all configurations."""

    hybrid: list[str]
    lexical: list[str]
    dense: list[str]
    fused: dict[str, float]
    similarity: dict[str, float]
    features: dict[str, dict[str, float]]


@dataclass
class Result:
    name: str
    per_query: dict[str, dict[str, float]] = field(default_factory=dict)

    def mean(self, metric: str) -> float:
        return statistics.fmean(v[metric] for v in self.per_query.values())


def score(ranked: list[str], judgments: dict[str, int]) -> dict[str, float]:
    return {
        "ndcg@10": m.ndcg_at_k(ranked, judgments, 10),
        "map@100": m.average_precision(ranked, judgments, 100),
        "mrr@10": m.reciprocal_rank(ranked, judgments, 10),
        "p@10": m.precision_at_k(ranked, judgments, 10),
        "recall@100": m.recall_at_k(ranked, judgments, 100),
    }


def lexical_rankings(session: Session, ds: TCDataset) -> dict[str, list[str]]:
    """Postgres FTS over the CVs, using production's query construction and normalisation."""
    docs = Table(
        "tc_eval_docs",
        MetaData(),
        Column("doc_id", Text, primary_key=True),
        Column("body", Text),
        Column("tsv", TSVECTOR),
        prefixes=["TEMPORARY"],
        postgresql_on_commit="DROP",
    )
    docs.create(session.connection())
    session.execute(
        insert(docs), [{"doc_id": d.doc_id, "body": d.text} for d in ds.resumes.values()]
    )
    # Computed inside Postgres in one statement (a bulk insert can't bind SQL functions).
    session.execute(update(docs).values(tsv=func.to_tsvector("english", docs.c.body)))
    out = {}
    for qid, job in ds.jobs.items():
        tsq = or_tsquery(job.text)
        rank = func.ts_rank_cd(docs.c.tsv, tsq, LEXICAL_RANK_NORMALIZATION)
        rows = session.execute(
            select(docs.c.doc_id)
            .where(docs.c.tsv.op("@@")(tsq))
            .order_by(rank.desc(), docs.c.doc_id)
            .limit(DEPTH)
        ).scalars()
        out[qid] = list(rows)
    session.rollback()  # drops the temporary table
    return out


def build_candidates(session: Session, ds: TCDataset, embedder: Embedder) -> dict[str, Candidates]:
    lexical = lexical_rankings(session, ds)
    doc_ids = list(ds.resumes)
    doc_vecs = embedder.encode_documents([ds.resumes[d].text for d in doc_ids])
    out: dict[str, Candidates] = {}
    for qid, job in ds.jobs.items():
        qvec = embedder.encode_queries([job.text])[0]
        sims = dict(zip(doc_ids, (doc_vecs @ qvec).tolist(), strict=True))
        dense = sorted(doc_ids, key=lambda d: (-sims[d], d))[:DEPTH]
        fused_list = reciprocal_rank_fusion({"lexical": lexical[qid], "dense": dense})[:DEPTH]
        fused = dict(fused_list)
        hybrid = [d for d, _ in fused_list]
        max_fused = max(fused.values())
        patterns = [_compile(s.lower()) for s in job.required_skills]
        jf = JobFacts(
            required_skill_ids=frozenset(range(len(patterns))), experience_min=job.experience_min
        )
        feats = {}
        for d in hybrid:
            text = ds.resumes[d].text.lower()
            cf = CandidateFacts(
                skill_ids=frozenset(i for i, p in enumerate(patterns) if p.search(text)),
                # We read the whole CV, so "no matches" is a known 0, not missing data.
                skills_known=bool(patterns),
                experience_years=ds.resumes[d].experience_years,
            )
            fv = compute_features(
                cf, jf, semantic_similarity=sims[d], retrieval_score=fused[d] / max_fused, now=NOW
            )
            feats[d] = fv.values
        out[qid] = Candidates(hybrid, lexical[qid], dense, fused, sims, feats)
    return out


def rerank_weighted(c: Candidates, ranker: WeightedRanker) -> list[str]:
    s = {d: sum(ranker.weights[f] * c.features[d][f] for f in FEATURE_NAMES) for d in c.hybrid}
    return sorted(c.hybrid, key=lambda d: (-s[d], c.hybrid.index(d)))


def rerank_cross_encoder(
    head_order: list[str], base_score: Callable[[str], float], ce: dict[str, float]
) -> list[str]:
    head = head_order[:CROSS_ENCODER_TOP_N]
    blended = {
        d: (1 - CROSS_ENCODER_BLEND) * base_score(d) + CROSS_ENCODER_BLEND * sigmoid(ce[d])
        for d in head
    }
    return sorted(head, key=lambda d: -blended[d]) + head_order[CROSS_ENCODER_TOP_N:]


def lambdamart_loqo(
    cands: dict[str, Candidates], qrels: dict[str, dict[str, int]], seed: int = 0
) -> dict[str, list[str]]:
    """Leave-one-query-out: train on 9 queries, rank the held-out one. Exploratory only."""
    from app.domains.evaluation.ltr import lambdamart_leave_one_query_out

    data = []
    for qid in sorted(cands):
        c = cands[qid]
        x = np.array([[c.features[d][f] for f in FEATURE_NAMES] for d in c.hybrid], dtype=float)
        y = np.array([1 if d in qrels[qid] else 0 for d in c.hybrid], dtype=np.int64)
        data.append((qid, x, y))
    scores = lambdamart_leave_one_query_out(data, seed)
    return {
        qid: [d for _, d in sorted(zip([-v for v in scores[qid]], cands[qid].hybrid, strict=True))]
        for qid in cands
    }


def paired(a: Result, b: Result, metric: str, seed: int = 0) -> tuple[float, float, float]:
    import random

    q = sorted(a.per_query)
    diffs = [b.per_query[i][metric] - a.per_query[i][metric] for i in q]
    rng = random.Random(seed)  # noqa: S311 (statistics, not security)
    means = sorted(
        statistics.fmean(rng.choices(diffs, k=len(diffs))) for _ in range(BOOTSTRAP_SAMPLES)
    )
    return (
        statistics.fmean(diffs),
        means[int(0.025 * BOOTSTRAP_SAMPLES)],
        means[int(0.975 * BOOTSTRAP_SAMPLES) - 1],
    )


def evaluate(
    session: Session, ds: TCDataset, embedder: Embedder, reranker: Reranker, ranker: WeightedRanker
) -> tuple[list[Result], dict[str, Any]]:
    qrels = {q: {d: RELEVANT for d in docs} for q, docs in ds.qrels.items()}
    cands = build_candidates(session, ds, embedder)
    rankings: dict[str, dict[str, list[str]]] = {
        "lexical (FTS)": {q: c.lexical for q, c in cands.items()},
        "dense (bge-small)": {q: c.dense for q, c in cands.items()},
        "hybrid (RRF k=60)": {q: c.hybrid for q, c in cands.items()},
        "hybrid + features (weighted_v1)": {
            q: rerank_weighted(c, ranker) for q, c in cands.items()
        },
    }
    skills_only = WeightedRanker(
        {f: (1.0 if f == "required_skill_coverage" else 0.0) for f in FEATURE_NAMES}, "skills_only"
    )
    rankings["hybrid + skill coverage only (ablation)"] = {
        q: rerank_weighted(c, skills_only) for q, c in cands.items()
    }

    ce_scores: dict[str, dict[str, float]] = {}
    for qid, c in cands.items():
        head = list(
            dict.fromkeys(
                rankings["hybrid + features (weighted_v1)"][qid][:CROSS_ENCODER_TOP_N]
                + c.hybrid[:CROSS_ENCODER_TOP_N]
            )
        )
        logits = reranker.score([(ds.jobs[qid].text, ds.resumes[d].text) for d in head])
        ce_scores[qid] = dict(zip(head, logits, strict=True))

    def stage1(c: Candidates) -> Callable[[str], float]:
        return lambda d: sum(ranker.weights[f] * c.features[d][f] for f in FEATURE_NAMES)

    def retrieval(c: Candidates) -> Callable[[str], float]:
        top = max(c.fused.values())
        return lambda d: c.fused[d] / top

    rankings["hybrid + features + cross-encoder"] = {
        q: rerank_cross_encoder(
            rankings["hybrid + features (weighted_v1)"][q], stage1(c), ce_scores[q]
        )
        for q, c in cands.items()
    }
    rankings["hybrid + cross-encoder only"] = {
        q: rerank_cross_encoder(c.hybrid, retrieval(c), ce_scores[q]) for q, c in cands.items()
    }
    rankings["LambdaMART, leave-one-query-out (EXPLORATORY)"] = lambdamart_loqo(cands, qrels)

    results = []
    for name, by_q in rankings.items():
        r = Result(name)
        for qid in sorted(qrels):
            r.per_query[qid] = score(by_q[qid], qrels[qid])
        results.append(r)
    info = {
        "n_queries": len(qrels),
        "n_docs": len(ds.resumes),
        "relevant_per_query": sorted(len(v) for v in qrels.values()),
        "skills_per_query": sorted(len(j.required_skills) for j in ds.jobs.values()),
        "resumes_with_experience": sum(r.experience_years is not None for r in ds.resumes.values()),
    }
    return results, info


def persist(session: Session, results: list[Result], info: dict[str, Any], dataset: str) -> None:
    for r in results:
        session.add(
            EvaluationRun(
                experiment_name="ranking_comparison",
                dataset_version=dataset,
                split="development",
                configuration={
                    "name": r.name,
                    "depth": DEPTH,
                    "cross_encoder_top_n": CROSS_ENCODER_TOP_N,
                    "cross_encoder_blend": CROSS_ENCODER_BLEND,
                },
                metrics={
                    "n_queries": len(r.per_query),
                    "mean": {k: round(r.mean(k), 4) for k in METRICS},
                    "per_query": r.per_query,
                    "dataset_info": info,
                },
                git_commit=git_commit(),
            )
        )
    session.commit()


def write_report(path: Path, results: list[Result], info: dict[str, Any], dataset: str) -> None:
    by = {r.name: r for r in results}
    base = by["hybrid (RRF k=60)"]
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    out = [
        f"# Ranking evaluation: {dataset}",
        "",
        f"Generated by `python -m app.cli eval-ranking` on {now}, commit `{git_commit()}`.",
        "**Every number below was computed by that command. Re-run it to reproduce.**",
        "",
        "Data: TalentCLEF 2026 Task A, development split, English (CC BY 4.0). Queries are job",
        "descriptions; documents are **synthetic CVs**; relevance labels are **human expert**",
        "judgments (binary). Attribution: TalentCLEF 2026 organisers, Zenodo record 19652670.",
        "",
        f"- {info['n_queries']} job queries · {info['n_docs']} CVs · relevant CVs per query: "
        f"{info['relevant_per_query']}",
        f"- Parsed required skills per job: {info['skills_per_query']} · CVs with parseable "
        f"experience: {info['resumes_with_experience']}/{info['n_docs']}",
        "- Salary, location, job type and recency are not present in this data, so those features",
        "  are neutral (0.5) for every CV and cannot affect the order.",
        f"- Depth {DEPTH}; cross-encoder on the top {CROSS_ENCODER_TOP_N}; "
        f"blend {CROSS_ENCODER_BLEND}.",
        "",
        "## Results (mean over queries)",
        "",
        "| Configuration | NDCG@10 | MAP@100 | MRR@10 | P@10 | R@100 |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        out.append(f"| {r.name} | " + " | ".join(f"{r.mean(k):.3f}" for k in METRICS) + " |")
    out += [
        "",
        f"## Difference vs `{base.name}` (paired bootstrap over the {info['n_queries']} "
        f"queries, {BOOTSTRAP_SAMPLES:,} resamples, 95% CI)",
        "",
        "| Configuration | ΔNDCG@10 | ΔMAP@100 |",
        "|---|---|---|",
    ]
    for r in results:
        if r is base:
            continue
        cells = []
        for metric in ("ndcg@10", "map@100"):
            d, lo, hi = paired(base, r, metric)
            cells.append(f"{d:+.3f} [{lo:+.3f}, {hi:+.3f}]" + (" ✱" if lo > 0 or hi < 0 else ""))
        out.append(f"| {r.name} | " + " | ".join(cells) + " |")
    out += [
        "",
        "✱ = 95% interval excludes 0. With 10 queries, intervals are wide.",
        "",
        "## NDCG@10 per query",
        "",
        "| Query | " + " | ".join(f"q{i}" for i in range(1, info["n_queries"] + 1)) + " |",
        "|---|" + "---|" * info["n_queries"],
    ]
    for r in results:
        out.append(
            f"| {r.name} | "
            + " | ".join(f"{r.per_query[q]['ndcg@10']:.2f}" for q in sorted(r.per_query))
            + " |"
        )
    out += [
        "",
        "LambdaMART is **exploratory**: 10 queries is below the 50-query threshold in",
        "ADR-011, so it is not used in production regardless of this result.",
        "",
    ]
    path.write_text("\n".join(out) + "\n")
