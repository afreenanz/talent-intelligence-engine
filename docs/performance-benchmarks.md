# Performance benchmarks

> Status: **Measured (Milestone 7B)**. Source: [eval/reports/2026-11-17-performance.md](../eval/reports/2026-11-17-performance.md),
> produced by `uv run python -m app.cli bench-performance` (from `backend/`). Re-run it to refresh;
> numbers vary a few ms between runs. Caching (Redis) is measured in Milestone 9.

**Environment:** laptop CPU (Apple Silicon; models on CPU for reproducibility), Postgres 17 + pgvector
in Docker, ~1,600 active jobs, warm process (first-request model loading of ~8–10 s per model excluded).

| Operation | p50 | p95 | Notes |
|---|---|---|---|
| Encode one query (bge-small) | 7.7 ms | 8.6 ms | |
| Retrieve top 100, lexical | 5.7 ms | 23 ms | p95 = first queries on a cold cache |
| Retrieve top 100, dense (exact) | 16.5 ms | 19.5 ms | includes query encoding |
| Retrieve top 100, hybrid | 20.5 ms | 31 ms | lexical + dense + RRF + title load |
| Rank 100 (stage 1 features) | 16.6 ms | 19.6 ms | one batched job/skill query |
| + cross-encoder on top 50 | **477 ms** | 681 ms | why stage 2 is opt-in |
| HTTP `POST /jobs/search` end to end | **54 ms** | 72 ms | auth, retrieval, ranking, personalization, search + impression logging |
| Document embedding throughput | 63 docs/s | | full job texts (~1,500 chars) |
| Agent turn (live Gemini, free tier) | 2.4–6.5 s | 4.8–12.6 s | from the agent benchmark; dominated by LLM calls |

## Indexing decisions (from EXPLAIN ANALYZE, warm cache)

| Query | Plan chosen | Finding / decision |
|---|---|---|
| Lexical FTS (OR tsquery) | Seq Scan on jobs, 8.5 ms | With seq scan disabled the planner uses `ix_jobs_search_vector` (Bitmap Index Scan) at 5.2 ms. The planner is slightly pessimistic about random I/O (default `random_page_cost=4` on an SSD). **Decision:** keep defaults at this size; set `random_page_cost≈1.1` in production. The GIN index is proven usable. |
| Dense exact | Seq Scan on job_embeddings + hash join, 1.4–3 ms | Exact scan is fast at 1.6k vectors. |
| Dense with HNSW (built, measured, rolled back) | Index Scan using HNSW, 1.4 ms vs 2.1 ms exact | Recall@10 vs exact 0.98–1.0; build 660 ms. **Decision: no HNSW yet.** It saves under 1 ms and costs build time, write overhead and slight recall loss. Revisit at ~50k+ vectors or p95 dense > 50 ms. `hnsw.iterative_scan` is already set for filtered queries. |

**A methodology bug caught along the way:** the first plan comparison ran the seq-scan plan on a cold cache
and the index plan on a warm one, which suggested a misleading 20 ms vs 8 ms gap. Stale statistics were ruled
out (autoanalyze had run; `ANALYZE` changed nothing). The benchmark now warms each query before `EXPLAIN ANALYZE`.

## Where time goes in a search request (p50 ≈ 54 ms)
query embedding ≈ 8 ms → lexical + dense SQL ≈ 12 ms → ranking ≈ 17 ms → search log + impressions insert
and response serialisation ≈ the rest. Next optimisations, only if needed: cache query embeddings and
repeated searches in Redis (Milestone 9); batch impression inserts asynchronously.
