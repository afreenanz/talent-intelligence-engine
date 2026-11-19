"""Reproducible retrieval evaluation: lexical vs dense vs hybrid (and embedding models).

Protocol
1. Load queries + graded judgments (eval/datasets/<version>/).
2. Map judged external_ids to the *currently retrievable* jobs (active, canonical).
   Judgments for expired/duplicate jobs are dropped (no system may return them) and counted.
3. Tune hybrid fusion parameters (rrf_k, dense weight) on the DEV split only.
4. Evaluate every configuration on the chosen split with identical queries and filters.
5. Compare against the lexical baseline with a paired bootstrap over queries (95% CI).
6. Persist one `evaluation_runs` row per configuration and write a Markdown report.
"""

import json
import random
import statistics
import subprocess
import time
import uuid
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import JobStatus
from app.domains.evaluation import metrics as m
from app.domains.evaluation.models import EvaluationRun
from app.domains.jobs.models import Job
from app.domains.search.schemas import JobFilters, RetrievalMode, RetrievalParams
from app.domains.search.service import retrieve_jobs
from app.integrations.embeddings.base import Embedder

METRIC_NAMES = ("ndcg@10", "ndcg@5", "mrr@10", "p@5", "p@10", "recall@10", "recall@100")
DEPTH = 100
BOOTSTRAP_SAMPLES = 10_000


@dataclass(frozen=True)
class Query:
    query_id: str
    text: str
    category: str
    split: str
    filters: dict[str, Any]


@dataclass
class Dataset:
    version: str
    queries: list[Query]
    judgments: dict[str, dict[uuid.UUID, int]]  # query_id -> {job_id: grade}
    dropped_judgments: int = 0
    source: str = "synthetic_v1"  # the feed the labels refer to; retrieval is scoped to it


@dataclass(frozen=True)
class Config:
    name: str
    mode: RetrievalMode
    model: str
    rrf_k: int = 60
    dense_weight: float = 1.0
    query_prefix: bool = True  # ablation switch for models with a query instruction


@dataclass
class ConfigResult:
    config: Config
    per_query: dict[str, dict[str, float]]
    latency_ms: list[float] = field(default_factory=list)

    def mean(self, metric: str, qids: list[str] | None = None) -> float:
        ids = qids if qids is not None else list(self.per_query)
        return statistics.fmean(self.per_query[q][metric] for q in ids)


def load_dataset(session: Session, directory: Path, source: str) -> Dataset:
    queries = [
        Query(q["query_id"], q["text"], q["category"], q["split"], q.get("filters") or {})
        for q in map(json.loads, (directory / "queries.jsonl").open())
    ]
    by_external = dict(
        session.execute(
            select(Job.external_id, Job.id).where(
                Job.source == source, Job.status == JobStatus.ACTIVE
            )
        ).all()
    )
    judgments: dict[str, dict[uuid.UUID, int]] = defaultdict(dict)
    dropped = 0
    lines = (directory / "qrels.tsv").read_text().splitlines()[1:]
    for line in lines:
        qid, ext, g = line.split("\t")
        job_id = by_external.get(ext)
        if job_id is None:
            dropped += 1
            continue
        judgments[qid][job_id] = int(g)
    problems = m.validate_judgments(judgments)
    if problems:
        raise ValueError(f"unusable judgments: {problems[:5]}")
    return Dataset(directory.name, queries, dict(judgments), dropped, source)


def score_query(ranked: list[uuid.UUID], j: dict[uuid.UUID, int]) -> dict[str, float]:
    return {
        "ndcg@10": m.ndcg_at_k(ranked, j, 10),
        "ndcg@5": m.ndcg_at_k(ranked, j, 5),
        "mrr@10": m.reciprocal_rank(ranked, j, k=10),
        "p@5": m.precision_at_k(ranked, j, 5),
        "p@10": m.precision_at_k(ranked, j, 10),
        "recall@10": m.recall_at_k(ranked, j, 10),
        "recall@100": m.recall_at_k(ranked, j, 100),
    }


def run_config(
    session: Session, dataset: Dataset, config: Config, embedder: Embedder, split: str
) -> ConfigResult:
    result = ConfigResult(config, {})
    params = RetrievalParams(depth=DEPTH, rrf_k=config.rrf_k, dense_weight=config.dense_weight)
    for q in dataset.queries:
        if q.split != split:
            continue
        started = time.perf_counter()
        r = retrieve_jobs(
            session,
            query=q.text,
            candidate_id=None,
            # Retrieve only from the labelled corpus: unlabelled jobs from other feeds would
            # otherwise be scored as misses and quietly lower every metric.
            filters=JobFilters(**q.filters, sources=[dataset.source]),
            top_k=DEPTH,
            embedder=embedder,
            mode=config.mode,
            params=params,
        )
        result.latency_ms.append((time.perf_counter() - started) * 1000)
        result.per_query[q.query_id] = score_query(
            [j.job_id for j in r.jobs], dataset.judgments[q.query_id]
        )
    return result


def paired_bootstrap(
    a: ConfigResult, b: ConfigResult, metric: str, seed: int = 0
) -> tuple[float, float, float]:
    """Mean difference (b - a) and 95% CI, resampling queries with replacement."""
    qids = sorted(a.per_query)
    diffs = [b.per_query[q][metric] - a.per_query[q][metric] for q in qids]
    rng = random.Random(seed)  # noqa: S311 (statistics, not security)
    n = len(diffs)
    means = sorted(statistics.fmean(rng.choices(diffs, k=n)) for _ in range(BOOTSTRAP_SAMPLES))
    return (
        statistics.fmean(diffs),
        means[int(0.025 * BOOTSTRAP_SAMPLES)],
        means[int(0.975 * BOOTSTRAP_SAMPLES) - 1],
    )


def tune_hybrid(
    session: Session, dataset: Dataset, embedder: Embedder, model: str
) -> tuple[Config, list[tuple[Config, float]]]:
    """Grid search on DEV only. Returns the best config and the full grid (for the report)."""
    grid = []
    for k in (10, 30, 60, 100):
        for w in (0.5, 1.0, 2.0):
            cfg = Config(f"hybrid k={k} w_dense={w}", "hybrid", model, rrf_k=k, dense_weight=w)
            grid.append((cfg, run_config(session, dataset, cfg, embedder, "dev").mean("ndcg@10")))
    best = max(grid, key=lambda item: (item[1], -abs(item[0].rrf_k - 60)))[0]
    return best, grid


def git_commit() -> str | None:
    try:
        sha = subprocess.run(
            ["/usr/bin/env", "git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["/usr/bin/env", "git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        return sha + ("-dirty" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return None


def persist(
    session: Session,
    experiment: str,
    dataset: Dataset,
    split: str,
    result: ConfigResult,
    categories: dict[str, str],
    extra: dict[str, Any],
) -> EvaluationRun:
    by_cat: dict[str, list[str]] = defaultdict(list)
    for qid in result.per_query:
        by_cat[categories[qid]].append(qid)
    lat = sorted(result.latency_ms)
    run = EvaluationRun(
        experiment_name=experiment,
        dataset_version=dataset.version,
        split=split,
        configuration={**asdict(result.config), "depth": DEPTH, **extra},
        metrics={
            "n_queries": len(result.per_query),
            "mean": {k: round(result.mean(k), 4) for k in METRIC_NAMES},
            "by_category": {
                cat: {k: round(result.mean(k, ids), 4) for k in ("ndcg@10", "mrr@10")}
                for cat, ids in sorted(by_cat.items())
            },
            "latency_ms": {
                "p50": round(lat[len(lat) // 2], 1),
                "p95": round(lat[int(len(lat) * 0.95) - 1], 1),
            },
            "per_query": result.per_query,
        },
        git_commit=git_commit(),
    )
    session.add(run)
    session.commit()
    return run


def write_report(
    path: Path,
    dataset: Dataset,
    split: str,
    results: list[ConfigResult],
    baseline: ConfigResult,
    grid: list[tuple[Config, float]],
    best: Config,
    categories: dict[str, str],
) -> None:
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    out = [
        f"# Retrieval evaluation: {dataset.version} ({split} split)",
        "",
        f"Generated by `python -m app.cli eval-retrieval` on {now}, commit `{git_commit()}`.",
        "**Every number below was computed by that command. Re-run it to reproduce.**",
        "",
        "> **Read this first.** Corpus and labels are *synthetic and rule-based (silver)*:",
        "> jobs come from templates; relevance comes from generator ground truth (see the",
        "> dataset README). Results compare systems *on this dataset*. They are not",
        "> evidence of real-world quality.",
        "",
        f"- Queries in split: {len(baseline.per_query)} · judgments dropped "
        f"(job no longer active): {dataset.dropped_judgments}",
        f"- Retrieval depth {DEPTH}; relevant = grade >= {m.RELEVANT_GRADE}; "
        "NDCG uses graded gain 2^g-1",
        "",
        "## Overall",
        "",
        "| Configuration | NDCG@10 | NDCG@5 | MRR@10 | P@5 | P@10 | R@10 | R@100 "
        "| p50 ms | p95 ms |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lat = sorted(r.latency_ms)
        cells = " | ".join(f"{r.mean(k):.3f}" for k in METRIC_NAMES)
        out.append(
            f"| {r.config.name} | {cells} | {lat[len(lat) // 2]:.0f} | "
            f"{lat[int(len(lat) * 0.95) - 1]:.0f} |"
        )
    out += [
        "",
        f"## Difference vs `{baseline.config.name}` (paired bootstrap, {BOOTSTRAP_SAMPLES:,} "
        "resamples, 95% CI)",
        "",
        "| Configuration | ΔNDCG@10 [95% CI] | ΔMRR@10 [95% CI] |",
        "|---|---|---|",
    ]
    for r in results:
        if r is baseline:
            continue
        diffs: list[str] = []
        for metric in ("ndcg@10", "mrr@10"):
            d, lo, hi = paired_bootstrap(baseline, r, metric)
            mark = " ✱" if lo > 0 or hi < 0 else ""
            diffs.append(f"{d:+.3f} [{lo:+.3f}, {hi:+.3f}]{mark}")
        out.append(f"| {r.config.name} | {' | '.join(diffs)} |")
    out += [
        "",
        "✱ = the 95% interval excludes 0. With ~20 queries, intervals are wide; treat small",
        "differences as noise.",
        "",
        "## NDCG@10 by query category",
        "",
    ]
    cats = sorted({categories[q] for q in baseline.per_query})
    out.append("| Configuration | " + " | ".join(cats) + " |")
    out.append("|---|" + "---|" * len(cats))
    for r in results:
        row = []
        for c in cats:
            ids = [q for q in r.per_query if categories[q] == c]
            row.append(f"{r.mean('ndcg@10', ids):.3f} (n={len(ids)})")
        out.append(f"| {r.config.name} | " + " | ".join(row) + " |")
    out += [
        "",
        "## Hybrid fusion tuning (DEV split only, NDCG@10)",
        "",
        "| rrf_k | dense weight 0.5 | 1.0 | 2.0 |",
        "|---|---|---|---|",
    ]
    for k in (10, 30, 60, 100):
        vals = [f"{s:.3f}" for c, s in grid if c.rrf_k == k]
        out.append(f"| {k} | " + " | ".join(vals) + " |")
    out += [
        "",
        f"Selected on dev: **rrf_k={best.rrf_k}, dense weight={best.dense_weight}**. It is",
        "evaluated above on the held-out split as `hybrid (tuned)`.",
        "",
    ]
    path.write_text("\n".join(out) + "\n")
