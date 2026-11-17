"""Performance benchmarks with the real models and the dev database.

Measures (all wall-clock, warm process unless stated):
- embedding: single-query latency, document batch throughput
- retrieval per mode over the retrieval_v1 queries (repeated)
- ranking: stage 1 for 100 candidates; cross-encoder for the top 50
- end-to-end HTTP latency of POST /api/v1/jobs/search (TestClient, in-process)
- Postgres plans (EXPLAIN ANALYZE) for the lexical and dense queries
- exact vector scan vs an HNSW index: latency and recall@10 overlap, in a rolled-back transaction
Caching (Redis) is Milestone 9 and is measured there.
"""

import json
import statistics
import time
from collections.abc import Callable
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.domains.evaluation.models import EvaluationRun
from app.domains.evaluation.retrieval_eval import git_commit
from app.domains.jobs.models import Job
from app.domains.ranking.cross_encoder import Reranker
from app.domains.ranking.service import rank_jobs
from app.domains.ranking.weighted import WeightedRanker
from app.domains.search import retrievers
from app.domains.search.indexing import job_text
from app.domains.search.schemas import JobFilters
from app.domains.search.service import retrieve_jobs
from app.integrations.embeddings.base import Embedder

REPEATS = 3


def _pct(values: list[float]) -> dict[str, float]:
    v = sorted(values)
    return {
        "n": len(v),
        "p50_ms": round(v[len(v) // 2], 1),
        "p95_ms": round(v[max(0, int(len(v) * 0.95) - 1)], 1),
        "mean_ms": round(statistics.fmean(v), 1),
    }


def _time(fn: Callable[[], Any]) -> float:
    t = time.perf_counter()
    fn()
    return (time.perf_counter() - t) * 1000


def embedding(embedder: Embedder, queries: list[str], docs: list[str]) -> dict[str, Any]:
    embedder.encode_queries(["warm up"])
    single = [_time(partial(embedder.encode_queries, [q])) for q in queries for _ in range(REPEATS)]
    t = time.perf_counter()
    embedder.encode_documents(docs, batch_size=64)
    secs = time.perf_counter() - t
    return {
        "query_encode": _pct(single),
        "document_throughput_per_s": round(len(docs) / secs, 1),
        "documents": len(docs),
    }


def retrieval(session: Session, embedder: Embedder, queries: list[str]) -> dict[str, Any]:
    out = {}
    for mode in ("lexical", "dense", "hybrid"):
        times = [
            _time(
                partial(
                    retrieve_jobs,
                    session,
                    query=q,
                    candidate_id=None,
                    filters=JobFilters(),
                    top_k=100,
                    embedder=embedder,
                    mode=mode,
                )
            )
            for q in queries
            for _ in range(REPEATS)
        ]
        out[mode] = _pct(times)
    return out


def ranking(
    session: Session, embedder: Embedder, reranker: Reranker, queries: list[str]
) -> dict[str, Any]:
    ranker = WeightedRanker.from_file()
    s1, ce = [], []
    for q in queries:
        r = retrieve_jobs(
            session, query=q, candidate_id=None, filters=JobFilters(), top_k=100, embedder=embedder
        )
        stage1 = partial(
            rank_jobs,
            session,
            r,
            ranker=ranker,
            candidate_id=None,
            query=q,
            embedding_model=embedder.spec.name,
        )
        with_ce = partial(
            rank_jobs,
            session,
            r,
            ranker=ranker,
            candidate_id=None,
            query=q,
            embedding_model=embedder.spec.name,
            stage="features+cross_encoder",
            reranker=reranker,
        )
        s1.append(_time(stage1))
        ce.append(_time(with_ce))
    return {"stage1_features_100_jobs": _pct(s1), "stage1_plus_cross_encoder_top50": _pct(ce)}


def _plan(session: Session, sql: str, params: dict[str, Any]) -> dict[str, Any]:
    # Warm the buffer cache first. Without this, whichever plan runs first looks slower: an early
    # version compared a cold seq-scan plan with a warm index plan and drew the wrong conclusion.
    session.execute(text(sql), params).all()
    rows = session.execute(
        text("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql), params
    ).scalar_one()
    plan = rows[0]
    nodes: list[str] = []

    def walk(node: dict[str, Any]) -> None:
        label = node["Node Type"] + (
            f" on {node['Relation Name']}" if "Relation Name" in node else ""
        )
        if "Index Name" in node:
            label += f" using {node['Index Name']}"
        nodes.append(label)
        for child in node.get("Plans", []):
            walk(child)

    walk(plan["Plan"])
    return {
        "execution_ms": round(plan["Execution Time"], 2),
        "planning_ms": round(plan["Planning Time"], 2),
        "nodes": nodes,
    }


LEXICAL_SQL = """
        SELECT id, ts_rank_cd(search_vector, t.q, 33) AS score
        FROM jobs,
             (SELECT replace(plainto_tsquery('english', :q)::text, '&', '|')::tsquery AS q) AS t
        WHERE status = 'active' AND search_vector @@ t.q ORDER BY score DESC, id LIMIT 100"""


def query_plans(session: Session, embedder: Embedder) -> dict[str, Any]:
    vec = embedder.encode_queries(["backend engineer python"])[0].tolist()
    lexical = _plan(session, LEXICAL_SQL, {"q": "backend engineer python"})
    dense = _plan(
        session,
        """
        SELECT j.id FROM jobs j JOIN job_embeddings e ON e.job_id = j.id
        WHERE e.embedding_model = :m AND j.status = 'active'
        ORDER BY e.embedding <=> CAST(:v AS vector) LIMIT 100""",
        {"m": embedder.spec.name, "v": str(vec)},
    )
    # At this corpus size the planner prefers a sequential scan. Forcing it off (in a SAVEPOINT)
    # shows the GIN index is usable when the table grows and the planner's costs change.
    with session.begin_nested():
        session.execute(text("SET LOCAL enable_seqscan = off"))
        forced = _plan(session, LEXICAL_SQL, {"q": "backend engineer python"})
    return {"lexical_fts": lexical, "lexical_fts_seqscan_disabled": forced, "dense_exact": dense}


def hnsw_vs_exact(session: Session, embedder: Embedder, queries: list[str]) -> dict[str, Any]:
    """Build an HNSW index inside a transaction, compare, and roll back (nothing is kept)."""
    model = embedder.spec.name
    vecs = [embedder.encode_queries([q])[0] for q in queries]

    def top10() -> tuple[list[list[str]], list[float]]:
        ids, times = [], []
        for v in vecs:
            t = time.perf_counter()
            hits = retrievers.dense_search(session, v, model, JobFilters(), 10)
            times.append((time.perf_counter() - t) * 1000)
            ids.append([str(j) for j, _ in hits])
        return ids, times

    exact_ids, exact_t = top10()
    t = time.perf_counter()
    session.execute(
        text("CREATE INDEX bench_hnsw ON job_embeddings USING hnsw (embedding vector_cosine_ops)")
    )
    build_ms = (time.perf_counter() - t) * 1000
    session.execute(text("SET LOCAL hnsw.ef_search = 40"))
    hnsw_ids, hnsw_t = top10()
    used = _plan(
        session,
        """SELECT job_id FROM job_embeddings WHERE embedding_model = :m
                             ORDER BY embedding <=> CAST(:v AS vector) LIMIT 10""",
        {"m": model, "v": str(vecs[0].tolist())},
    )["nodes"]
    session.rollback()  # drops the index
    overlap = [
        len(set(a) & set(b)) / max(1, len(a)) for a, b in zip(exact_ids, hnsw_ids, strict=True)
    ]
    n_vectors = session.scalar(
        text("SELECT count(*) FROM job_embeddings WHERE embedding_model = :m"), {"m": model}
    )
    return {
        "vectors": n_vectors,
        "exact": _pct(exact_t),
        "hnsw": _pct(hnsw_t),
        "hnsw_build_ms": round(build_ms, 1),
        "recall_at_10_vs_exact": round(statistics.fmean(overlap), 3),
        "hnsw_plan_nodes": used,
    }


def http_search(queries: list[str]) -> dict[str, Any]:
    """End-to-end through FastAPI (auth, validation, retrieval, ranking, logging, serialisation)."""
    from fastapi.testclient import TestClient

    from app.db.session import get_sessionmaker
    from app.domains.auth.models import User
    from app.main import app

    email = "perf-bench@example.com"  # .invalid is rejected by the email validator
    with TestClient(app) as c:
        c.post("/api/v1/auth/register", json={"email": email, "password": "perf-bench-password"})
        tok = c.post(
            "/api/v1/auth/login", json={"email": email, "password": "perf-bench-password"}
        ).json()
        h = {"Authorization": f"Bearer {tok['access_token']}"}
        c.post("/api/v1/jobs/search", json={"query": "warm up"}, headers=h)
        times = [
            _time(partial(c.post, "/api/v1/jobs/search", json={"query": q, "top_k": 20}, headers=h))
            for q in queries
        ]
    with get_sessionmaker()() as s:  # remove the benchmark user (cascades to its search logs)
        user = s.scalar(select(User).where(User.email == email))
        if user:
            s.delete(user)
            s.commit()
    return {"post_jobs_search_features": _pct(times)}


def run(
    session: Session, embedder: Embedder, reranker: Reranker, queries_file: Path
) -> dict[str, Any]:
    queries = [json.loads(line)["text"] for line in queries_file.open()]
    docs = [job_text(j) for j in session.scalars(select(Job).limit(256))]
    results = {
        "corpus_active_jobs": session.scalar(
            text("SELECT count(*) FROM jobs WHERE status = 'active'")
        ),
        "embedding": embedding(embedder, queries, docs),
        "retrieval": retrieval(session, embedder, queries),
        "ranking": ranking(session, embedder, reranker, queries[:15]),
        "query_plans": query_plans(session, embedder),
        "hnsw_vs_exact": hnsw_vs_exact(session, embedder, queries),
    }
    results["http"] = http_search(queries[:20])
    return results


def persist_and_report(session: Session, results: dict[str, Any], report: Path) -> None:
    session.add(
        EvaluationRun(
            experiment_name="performance",
            dataset_version="retrieval_v1 queries",
            split="all",
            configuration={"repeats": REPEATS, "device": "cpu"},
            metrics=results,
            git_commit=git_commit(),
        )
    )
    session.commit()
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    r = results

    def row(name: str, p: dict[str, Any]) -> str:
        return f"| {name} | {p['n']} | {p['p50_ms']} | {p['p95_ms']} |"

    hv = r["hnsw_vs_exact"]
    out = [
        "# Performance benchmark",
        "",
        f"Generated by `python -m app.cli bench-performance` on {now}, commit `{git_commit()}`.",
        "Laptop CPU (Apple Silicon, models on CPU), local Postgres in Docker, "
        f"{r['corpus_active_jobs']} active jobs.",
        "Warm process. First-request model loading (~8-10 s per model) is excluded.",
        "",
        "## Latency",
        "",
        "| Operation | n | p50 ms | p95 ms |",
        "|---|---|---|---|",
        row("encode one query (bge-small)", r["embedding"]["query_encode"]),
        *[row(f"retrieve top 100: {m}", p) for m, p in r["retrieval"].items()],
        row("rank 100 (stage 1 features)", r["ranking"]["stage1_features_100_jobs"]),
        row("rank 100 + cross-encoder top 50", r["ranking"]["stage1_plus_cross_encoder_top50"]),
        row("HTTP POST /jobs/search (end to end)", r["http"]["post_jobs_search_features"]),
        "",
        f"Document embedding throughput: **{r['embedding']['document_throughput_per_s']} docs/s** "
        f"({r['embedding']['documents']} job texts, batch 64).",
        "",
        "## Query plans (EXPLAIN ANALYZE)",
        "",
        f"- Lexical FTS: {r['query_plans']['lexical_fts']['execution_ms']} ms. "
        f"Plan: {' → '.join(r['query_plans']['lexical_fts']['nodes'])}",
        f"- Lexical FTS with seq scan disabled: "
        f"{r['query_plans']['lexical_fts_seqscan_disabled']['execution_ms']} ms. Plan: "
        f"{' → '.join(r['query_plans']['lexical_fts_seqscan_disabled']['nodes'])}",
        f"- Dense exact: {r['query_plans']['dense_exact']['execution_ms']} ms. "
        f"Plan: {' → '.join(r['query_plans']['dense_exact']['nodes'])}",
        "",
        "## Exact scan vs HNSW (index built and dropped inside a transaction)",
        "",
        f"{hv['vectors']} vectors. HNSW build: {hv['hnsw_build_ms']} ms. "
        f"Recall@10 of HNSW vs exact: **{hv['recall_at_10_vs_exact']}**.",
        "",
        "| Search | p50 ms | p95 ms |",
        "|---|---|---|",
        f"| exact | {hv['exact']['p50_ms']} | {hv['exact']['p95_ms']} |",
        f"| HNSW (ef_search=40) | {hv['hnsw']['p50_ms']} | {hv['hnsw']['p95_ms']} |",
        "",
        f"HNSW plan: {' → '.join(hv['hnsw_plan_nodes'])}",
        "",
    ]
    report.write_text("\n".join(out) + "\n")
