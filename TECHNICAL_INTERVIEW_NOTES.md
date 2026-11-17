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

## Milestone 1: Backend foundation
14. Why store only a SHA-256 hash of refresh tokens, yet use Argon2 for passwords? *(`app/core/security.py`: entropy argument)*
15. Walk through refresh-token rotation. What happens when an old refresh token is used again, and why log the user out everywhere? *(`auth/service.py::refresh`)*
16. Why does `refresh` use `SELECT ... FOR UPDATE`? What race does it prevent?
17. How does login avoid revealing whether an email is registered (message *and* timing)? Where does registration still reveal it, and why is that accepted?
18. Why hard-code `algorithms=["HS256"]` when decoding a JWT? What is the `alg: none` attack? *(test: `test_unsigned_alg_none_token_rejected`)*
19. Access tokens are stateless, so why does `get_current_user` still query the DB on every request?
20. How do the tests isolate each other while services call `session.commit()`? (outer transaction + `join_transaction_mode="create_savepoint"`)
21. Why test against real Postgres instead of SQLite?
22. Why is the salary rule enforced in both Pydantic and a DB `CHECK` constraint?
23. What doesn't Alembic autogenerate catch? (ENUM types on downgrade, extensions) How do we detect model/migration drift? (`alembic check` in CI)
24. How does `resolve_or_create_skills` stay O(1) in queries and safe under concurrent inserts? (`IN` lookups + `ON CONFLICT DO NOTHING`)
25. Why are ownership checks structural (no profile ID in any URL) rather than "check owner_id == user.id" on each request?
26. Liveness vs readiness: what does an orchestrator do differently on each failing?
27. Why sync endpoints with a threadpool instead of `async def` everywhere? *(ADR-004)*
