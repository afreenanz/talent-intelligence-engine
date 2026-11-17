# Retrieval Engine

> Status: **Design (Milestone 0)**. Implementation is in Milestone 3.

## Interface

```python
def retrieve_jobs(
    query: str | None,
    candidate_id: UUID | None,
    filters: JobFilters,          # location, location_type, salary_min, experience, employment_type
    top_k: int = 20,
    mode: Literal["lexical", "dense", "hybrid"] = "hybrid",
    params: RetrievalParams = RetrievalParams(),   # depth, rrf_k, weights
) -> list[RetrievedJob]
```
`RetrievedJob` = `job_id, title, company, lexical_rank, semantic_rank, lexical_score,
similarity, fused_score`. Ranks are `None` when a retriever did not return that job.

If `query` is empty and `candidate_id` is given, the dense query vector is the
**candidate embedding** and the lexical query is built from the candidate's top skills.
That is the "recommendations" path.

## A. Lexical retrieval
- Query parsing: `websearch_to_tsquery('english', :q)`, which never raises on user input and supports `"phrases"`, `or` and `-exclusion`.
- Document: weighted `tsvector` (title A, company/skills B, description C).
- Score: `ts_rank_cd(search_vector, query, 1|32)` (cover density, length-normalized, scaled to 0–1).
- Filters: plain SQL `WHERE` on indexed columns, applied **before** ranking.

**Limitations (documented, measured):**
1. No IDF. A common word ("engineer") weighs as much as a rare one ("Kubernetes"). This is the main gap versus BM25.
2. Stemming can merge unrelated terms, and technical tokens like `C++`, `C#` and `.NET` are mangled by the English parser. Mitigation: skills are matched separately via `job_skills` and fed to the ranker as features.
3. No synonymy ("SWE" vs "software engineer"). This is the gap dense retrieval is meant to fill.

*Optional experiment:* an in-memory BM25 (`rank_bm25`) over the same corpus, used only
as an evaluation baseline to quantify how much limitation 1 costs.

## B. Dense retrieval
- Model: configurable, with a 384-d default (ADR-005). Normalized embeddings, cosine distance `<=>`.
- Documents: `title + skills + first N tokens of description`. The text template is versioned, because changing it changes `content_hash`, which triggers re-embedding.
- Query: encoded with the model's query prompt where one exists (bge).
- Index: exact scan first; HNSW (`m=16, ef_construction=64`, `hnsw.ef_search` tuned) once benchmarks show the exact scan is slow. With filters, `hnsw.iterative_scan = relaxed_order`.
- The query embedding is cached in Redis keyed by `(model, sha256(query))`.

## C. Hybrid: Reciprocal Rank Fusion

```
fused(d) = Σ_r  w_r / (k + rank_r(d))      r ∈ {lexical, dense}, k = 60 by default
```
- RRF uses **ranks, not scores**, so it needs no score calibration between `ts_rank_cd` (0–1, no IDF) and cosine similarity (a different distribution). That is the main reason to choose it over weighted score fusion.
- A document missing from one list contributes 0 from that list.
- `k` controls how much the top ranks dominate. `k`, the weights and the retrieval depth (default 100 per retriever) are tuned on a **dev split** and reported on a **test split**.

## Evaluation
Precision@K, Recall@K, MRR and NDCG@K (graded labels), compared across lexical, dense and hybrid. See [evaluation-framework.md](evaluation-framework.md).
