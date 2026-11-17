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

## Milestone 4B: Ranking evaluation on real labels
77. What is TalentCLEF Task A? Why is it a valid test of a job -> candidate *and* candidate -> job ranker?
78. Why parse CVs deterministically instead of with the LLM here? (privacy, reproducibility, free tier)
79. Why use each job's own skill list as the vocabulary? What does that measure, and what doesn't it?
80. Features improved MAP but not NDCG@10. What does that tell you about *where* in the list they help?
81. The cross-encoder helped on real data but not obviously on synthetic. Why might that be?
82. Dense alone beat hybrid at the top. Why did you *not* re-weight hybrid on these results?
83. What is leave-one-query-out cross-validation, and why is LambdaMART still not in production?
84. Explain the torch + LightGBM crash and why a spawned worker process fixes it.
85. Why does "no skills matched" need to be 0, not "missing"? (skills_known)
86. Why pin a checksum for a downloaded dataset?

## Milestone 5A: Activity & explicit preferences
87. Why log impressions server-side instead of trusting the client? What does an impression give you that a click alone doesn't?
88. Why are `saved_jobs` (state) and `job_interactions` (events) written in the same transaction?
89. How is saving idempotent, and why does a repeated save *not* create a second event? (INSERT ... ON CONFLICT DO NOTHING RETURNING)
90. Walk through the application state machine. Why are rejected/withdrawn terminal? Why return the allowed transitions in the 409?
91. Why a fixed preference vocabulary instead of free-text memories?
92. Why does a preference write return the previous value? (the agent will say "changed from X to Y")
93. Bug found: `updated_at` wasn't changing on upsert. Why doesn't `onupdate=` fire for INSERT ... ON CONFLICT?
94. Bug found: a bad preference value produced a 500. Why, and why is a 422 with details the right answer?
95. Bug found: search logging silently didn't apply after a formatter change. What process change prevents that? (asserting every scripted edit; tests that check the behaviour, not just the code)

## Milestone 5B: Personalization
96. Why doesn't a bare click count as a positive signal? When does it count?
97. Why are impressions without clicks *not* negative feedback? (position bias, skimming)
98. Why the support threshold (≥ 3 jobs) and confidence < 1 for derived preferences?
99. Why does an explicit preference beat a derived one? Which profile facts can an explicit preference override, and why?
100. Why is the adjustment capped at ±0.1? What exactly does the cap protect against, and what does it cost (the ML/frontend personas)?
101. The v1 experiment learned nothing for the backend persona. Explain the feedback loop, and how exploration slots break it.
102. Why can't re-ranking alone surface jobs the retriever never returned? How does the preference channel fix it?
103. Why evaluate on *un-interacted* jobs only? What would go wrong otherwise?
104. Why is the persona experiment not evidence of real-user benefit? What would you need instead? (online A/B test, logged real behaviour)
105. Cold start for users and for jobs: what happens in each case, and why is "no popularity signal" a feature?

## Milestone 6A: AI agent
106. Draw the agent graph. Which edges are conditional, and on what?
107. Why stateless (`store: false`) LLM calls? What must you replay exactly, and why do thought signatures matter?
108. Why must every function_call get a result before the next model call? What happens in the step-limit path?
109. Explain `interrupt()` + `Command(resume=...)`. Why must the confirm node have no side effects before interrupt()? How did you verify it?
110. Where does `candidate_id` come from, and why is an LLM-supplied one rejected?
111. How does the grounding check work? What does it catch, and what can't it catch? (correct id, wrong salary)
112. Why one corrective retry and then `grounded=false` instead of hiding the answer?
113. Why rebuild the candidate context from the DB on every model call instead of trusting chat history?
114. Why two persistence paths (checkpoints + messages)? Why put LangGraph's tables in their own schema?
115. Bug: messages came back in random order in tests. Why does `now()` cause that, and why is `seq` the right fix?
116. How do you test an LLM agent deterministically? (scripted LLM turns that depend on real tool results)
117. The live agent added an unrequested filter. How would you measure and reduce that? (Milestone 7 benchmark)

## Milestone 7A: Evaluating LLM systems
118. Why deterministic checks rather than LLM-as-judge? What can deterministic checks *not* measure?
119. How is "factual consistency" computed for agent replies? What error would it still miss?
120. The first agent run had 6 failures. Why were they excluded from quality metrics, and why are they still reported?
121. 23/23 passed. List three weaknesses you found anyway, and why the checks didn't catch them.
122. Why run the benchmark twice? What does variation between runs tell you about LLM systems?
123. How did the extraction benchmark reveal that *your* code reintroduced a prompt injection? What was the fix and its trade-off?
124. Why is the v2 extraction score optimistic? What would a proper confirmation look like?
125. Why must thinking tokens be counted in the cost estimate?
126. How do you stay within a free tier's rate limits in batch jobs? (pacing, Retry-After, backoff)

## Milestone 7B: Performance
127. Walk through where the 54 ms of a search request goes. What would you optimise first, and why not before measuring?
128. Why isn't there an HNSW index? What numbers would change your mind?
129. The planner chose a seq scan over the GIN index. Why might that be right at 1.6k rows, and what is random_page_cost?
130. Your first plan comparison was wrong. What confounded it, and how did you rule out stale statistics?
131. Why is the cross-encoder opt-in? Quote its latency.
132. Why can only the retrieval benchmark be started over HTTP?
