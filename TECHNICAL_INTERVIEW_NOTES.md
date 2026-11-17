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

## Milestone 2A: Job ingestion
28. What makes the import idempotent? What exactly is in the content hash, and why hash *normalized* rather than raw fields?
29. Why does each record run in a SAVEPOINT, and why commit every 500 records instead of once at the end, or after every record?
30. Walk through near-duplicate detection: blocking key, shingles, Jaccard, threshold. Why not MinHash/LSH here? At what scale would you switch?
31. The first dedup version had recall 0.775 on injected duplicates. What was the cause, and what is the lifetime rule? (docs/ingestion.md)
32. Why keep duplicates as linked rows instead of deleting them?
33. Snapshot vs incremental feeds: what does the safety valve protect against?
34. Why does unparseable salary become NULL rather than a best guess? How will the ranker treat NULL?
35. Why are "Go", "R" and "rest" excluded from text skill matching? What precision/recall trade-off does that make?
36. Keyset vs OFFSET pagination: two concrete problems OFFSET has. Why fetch `limit + 1` rows?
37. Why is `listed_at` a separate column from `posted_at`?
38. Your dedup scores 1.0/1.0. Why shouldn't you claim that in an interview without qualification?

## Milestone 2B: Resume intelligence
39. Where exactly can the LLM "invent" something, and what deterministic control catches each case? (docs/resume-intelligence.md table)
40. Why is `experience_years` computed from date ranges instead of asked of the LLM? How are overlapping jobs handled?
41. Why does the upload return 202 instead of 200? What happens to the work if the server restarts (and how does Milestone 9 fix it)?
42. How does the atomic claim (`UPDATE ... WHERE status IN (...) RETURNING`) prevent double processing?
43. Why check magic bytes instead of the Content-Type header? Why is the user's filename never used in the storage path?
44. Why return 404 rather than 403 for someone else's resume?
45. Why a REST adapter over the SDK here? What would make you switch back?
46. The first live call failed with HTTP 400. What was the bug and how did you find it? (schema `title` stripping)
47. How does the prompt defend against injection inside the resume, and why isn't the prompt the main defence?
48. Why does the test suite force GEMINI_API_KEY to empty? What could go wrong otherwise?
49. Free-tier data may be used for training. What does that change about how you test?

## Milestone 3A: Retrieval engine
50. Why OR the query terms for lexical retrieval? What does AND do to a query like "python backend bangalore startup"?
51. Why cast the rewritten query straight to `tsquery` instead of passing it through `to_tsquery` again? (double stemming)
52. Why is `search_vector` a GENERATED column, and why does `skills_text` exist?
53. Derive why a document ranked #2 by both retrievers always beats one ranked #1 by a single retriever under RRF (any k > 0). When does k matter? (test_k_controls_consensus_vs_single_top_hit)
54. What is the bge query instruction, why does it only apply to queries, and how did you notice it was missing?
55. Why exact vector scan instead of HNSW right now? What would make you add the index, and what does `hnsw.iterative_scan` solve?
56. Why keep jobs with unknown salary when a salary filter is applied? What's the trade-off?
57. How do you avoid re-embedding unchanged jobs? What would force a full re-embed?
58. Why use a hashing embedder in most tests, plus a few tests with the real model?
59. Why the CPU-only torch index for Linux?

## Milestone 3B: Retrieval evaluation
60. Define P@K, R@K, MRR and NDCG@K. Why exponential gain? Why must IDCG use *all* judged documents, not just the retrieved ones?
61. Why is Recall@10 tiny here, and why is that not a bug?
62. What are "silver" labels? Why are yours independent of the systems, and what are their weaknesses?
63. Why tune on dev and report on test? What happened when you did (the tuned setting gained +0.005 on test)?
64. Explain the paired bootstrap. Why *paired*? What does a CI of [-0.001, +0.120] let you claim?
65. The model ranking flipped between splits. What does that tell you, and what would you need to decide properly?
66. Lexical search scored 0.30 on abbreviation queries. Why exactly, and how do dense embeddings help?
67. Why store per-query scores and the git commit with every evaluation run?
68. Which public datasets did you reject, and why does "no licence" mean you can't use it?

## Milestone 4A: Ranking engine
69. Why separate retrieval (recall) from ranking (precision)? Why rank 100 retrieved jobs, not the whole corpus?
70. Walk through each feature's rule, especially the asymmetric experience decay and the "neutral 0.5 for missing" policy. What would go wrong with 0 for missing?
71. Why do skills *mentioned in the text* stand in for "required" when a posting has no list?
72. Why a weighted linear model first? How do explanations fall out of it?
73. Bi-encoder vs cross-encoder: why is the cross-encoder more accurate and more expensive? Why only the top 50?
74. The first blending used per-list min-max and put all top-5 jobs in the wrong city. Explain exactly why. Why does the sigmoid fix it?
75. Why are explanations built from features instead of generated by an LLM?
76. Why is the cross-encoder loaded lazily, through a provider dependency?
