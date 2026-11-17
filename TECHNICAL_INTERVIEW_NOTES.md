# Technical Interview Notes

Questions you should be able to answer without notes, grouped by milestone. Answers point
to the doc that justifies them. Add your own answer in your own words under each one; that
is the actual exercise.

## Milestone 0: Architecture
1. Why a modular monolith instead of microservices? *(ADR-001)*
2. Why keep vectors in Postgres instead of a dedicated vector DB? What do you give up? *(ADR-003)*
3. PostgreSQL `ts_rank` is not BM25. What exactly is missing, and why does it matter for queries like "kubernetes engineer"? *(retrieval-engine.md, Lexical limitations)*
4. Why Reciprocal Rank Fusion rather than adding normalized scores? *(retrieval-engine.md §C)*
5. Why does HNSW + a `WHERE` clause sometimes return fewer than K rows, and what does `hnsw.iterative_scan` change? *(database-design.md §4)*
6. Why are embeddings in a separate table, and how do you avoid re-embedding unchanged jobs? *(database-design.md §3.5)*
7. Why log impressions? How does that help interpret clicks? *(database-design.md §3.3)*
8. Why are `saved_jobs` and `job_interactions` both needed? *(database-design.md §3.2)*
9. Why does the agent never receive `candidate_id` as a tool argument? *(agent-architecture.md, Tools)*
10. LangGraph re-runs a node from the top after `interrupt()`. What bug does that cause if you write to the DB before the interrupt? *(agent-architecture.md, confirm node)*
11. Why not use LangGraph's `PostgresStore` for preferences? *(ADR-009)*
12. Your evaluation labels are self-made on synthetic data. What can and can't you claim from the results? *(ADR-010)*
13. When is learning-to-rank *not* worth training? *(ADR-011)*
