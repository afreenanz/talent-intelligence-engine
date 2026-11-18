# Engineering Decisions (ADR log)

Each record has the format: context → decision → alternatives considered → consequences.
Status is one of: **Proposed** (awaiting approval), **Accepted**, **Superseded**.

---

## ADR-001 Modular monolith, not microservices — *Proposed*
**Context.** One developer, one database, and modules that share data heavily (ranking reads jobs, profiles, interactions and embeddings).
**Decision.** A single FastAPI deployable with domain packages, plus Celery workers that run from the same codebase.
**Alternatives.** Separate search, agent and ingestion services. Rejected: they would add network hops, distributed transactions and deployment overhead, with no scaling need to justify it.
**Consequences.** Module boundaries are enforced by convention and code review, not by the network. Any module can be extracted later because its dependencies go through service interfaces.

## ADR-002 Python 3.13 — *Proposed*
**Context.** The machine has Python 3.14.5 (python.org build, missing SSL certificates) and 3.11.16 (Homebrew). PyTorch 2.15, scikit-learn 1.9, SQLAlchemy 2.1 and mypy all publish macOS-arm64 wheels for 3.11–3.15. LangChain-core requires ≥3.11.
**Decision.** Target **Python 3.13** locally (via `uv`) and in Docker (`python:3.13-slim`).
**Alternatives.** 3.14 is supported by the core libs, but it is the newest release and transitive ML dependencies are the most likely to lag. 3.11 is close to end of life (Oct 2027).
**Consequences.** We need to install `uv` (or Homebrew `python@3.13`). CI pins the same version.

## ADR-003 PostgreSQL for everything stateful (search, vectors, memory, checkpoints, eval)
**Context.** The brief asks for lexical, vector and relational queries, plus persistent memory.
**Decision.** PostgreSQL 17 + pgvector. Full-text search uses `tsvector`, ANN uses HNSW, and agent checkpoints use `langgraph-checkpoint-postgres`.
**Alternatives.** Elasticsearch/OpenSearch (real BM25, but a second datastore to keep in sync). Qdrant/Pinecone for vectors (better ANN filtering, but data duplication and no joins with the profile/skill tables).
**Consequences.** Hybrid search is one SQL round-trip, and filters and joins are trivial. Cost: PostgreSQL `ts_rank` is **not BM25**, since it has no IDF and no k1/b saturation (see retrieval-engine.md). We document that and evaluate it rather than pretending otherwise.

## ADR-004 Synchronous endpoints + sync SQLAlchemy by default
See architecture.md §3. Async is reserved for the streaming agent endpoint if it is measured to need it.

## ADR-005 Default embedding model: `BAAI/bge-small-en-v1.5`; comparison: `all-MiniLM-L6-v2`
**Context.** CPU inference on a laptop, a corpus of thousands of jobs, English text.
**Decision.** Both are 384-dimensional, so they fit the same `vector(384)` column. bge-small is the default candidate and MiniLM is the comparison. The **final default is chosen by our own retrieval evaluation**, not by leaderboard numbers. The model name is configurable via env.
**Alternatives.** Larger models (bge-base 768-d, e5-large) are slower on CPU; they can be added as experiments. API embeddings (OpenAI) add cost and a network dependency to every search.
**Consequences.** Note that bge models expect a query instruction prefix for retrieval queries. The embedding service will handle query vs. document encoding explicitly.
**Update (Milestone 3B, 2026-11-17):** evaluated both models on `retrieval_v1`. The winner **flips between dev and test** (bge +0.09 on dev, MiniLM +0.06 on test), so the synthetic benchmark can't decide. bge stays the default. The decision is reopened when a real, human-labelled dataset is added. The bge query prefix is now set explicitly (its ST config ships empty); its effect was +0.04 on dev and neutral on test.

## ADR-006 Embeddings in their own tables with a content hash
See database-design.md §3.5.

## ADR-007 Cross-encoder: `cross-encoder/ms-marco-MiniLM-L6-v2`
**Context.** Reranking the top ~50 hybrid results per request on CPU.
**Decision.** MiniLM-L6. Its published scores are 74.30 NDCG@10 on TREC DL19 at about 1800 docs/s, against 74.31 for L12 at about half the speed (sbert.net pretrained models page).
**Caveat.** It is trained on MS MARCO web passages, not job matching. Whether it helps here is an empirical question, and **it may hurt**. The evaluation will say which.

**Update (Milestone 4A):** implemented for the top 50. Blending uses the model's sigmoid, not per-list min-max (see ranking-engine.md for the live failure that ruled min-max out). Usefulness is measured in 4B.

**Update (Milestone 4B, TalentCLEF, human labels):** features + cross-encoder gave the best MAP@100 (+0.067 vs hybrid, 95% CI [+0.038, +0.106]). The cross-encoder is kept as an opt-in stage because of its ≈0.5 s cost.

## ADR-008 LLM provider abstraction with three adapters
**Decision.** A `LLMProvider` protocol with `generate_structured(schema, messages)` and `chat_with_tools(messages, tools)`. Adapters: Gemini, OpenAI, and an **OpenAI-compatible local endpoint** (Ollama/LM Studio) as the clearly labelled local-development alternative. A deterministic scripted fake exists **only in the test suite** and is never selectable at runtime.
**Provider choice (2026-11-17):** Gemini free tier is the default. OpenRouter (free models) is the secondary option through the OpenAI-compatible adapter. Free-tier rate limits are checked when the integration is built (Milestone 2), and the model name is recorded in every evaluation run.
**Why.** This satisfies the rule "do not silently replace a failed integration with a fake implementation". If the configured provider is down, the API returns `503 upstream_unavailable` and never falls back silently.

**Update (Milestone 2B, 2026-11-17) — implemented and Accepted:**
- Implemented as a thin REST adapter over the Gemini **Interactions API** with `httpx`, not the
  `google-genai` SDK: `generateContent` returned 404 for current free-tier models and the docs had
  moved to `interactions.create`, so a small adapter over the verified REST contract (pinned with
  `Api-Revision`) is easier to test (mock transport) and reason about.
- Default model `gemini-3.5-flash-lite`, chosen by measurement: ~7–13 s per call, while `gemini-3.8-flash`
  timed out at the 600 s server deadline on the free tier.
- Retries: 429/5xx/timeouts, 2 retries with exponential backoff; 4xx is not retried.
- Free-tier data may be used by Google to improve products → only fictional or own resumes.
- The OpenAI-compatible adapter is not built yet; it will be added when needed (Milestone 6 agent work).

## ADR-009 Agent memory: own tables, LangGraph checkpointer for execution state only
**Context.** LangGraph offers a checkpointer for thread state and a `PostgresStore` for long-term memory.
**Decision.**
- LangGraph `PostgresSaver` stores **graph execution state** (needed for `interrupt()`/resume of confirmations).
- Our own `messages` table is the **user-facing conversation history** (a stable schema the frontend reads).
- Our own `agent_memory` table holds **preferences** (typed, confidence-scored, user-editable via REST).
**Alternatives.** Use `PostgresStore` for preferences. Rejected: its values are schemaless JSON in LangGraph-managed tables, which makes them harder to constrain, migrate with Alembic, expose for editing, and use in the LLM-independent ranker.
**Consequences.** There are two persistence paths to keep consistent. The ranking engine reads preferences without importing any LangGraph code.

## ADR-010 Evaluation labels: hand-labelled qrels with written guidelines
**Context.** No public dataset combines Indian/global job postings with candidate-relevance labels under a clear licence.
**Decision.** Build a versioned evaluation set (`eval/datasets/v1/`) of queries and candidate profiles with graded relevance labels (0–3), written according to `eval/labelling-guidelines.md`, **before** looking at system output for those queries. Use pooling: label the union of the top-20 results from every pipeline, so no single pipeline is favoured.
**Known weakness.** The labeller and the system builder are the same person, and the jobs are synthetic. Results show relative differences between pipelines on this dataset; they are **not** claims about real-world performance. This is stated in every report.
**Alternatives considered.** LLM-as-judge labels, which may be used as a secondary signal and must be reported with their agreement against human labels. Public datasets (e.g. Kaggle job-posting dumps) will have their licences checked before use; until they are verified, they are not used.

## ADR-011 Learning-to-rank is gated on data
LambdaMART (LightGBM `lambdarank`) is trained **only if** we have at least a few hundred labelled query-job pairs across ≥ 50 queries. Otherwise the experiment is reported as "insufficient data". Below that threshold it would just memorize the labels.

**Update (Milestone 4B):** run as an exploratory leave-one-query-out experiment on TalentCLEF (10 queries). It gained +0.048 MAP vs hybrid, which is less than features + cross-encoder. By this ADR's threshold it is not used in production. LightGBM runs in a spawned worker process: in one process with PyTorch on macOS it segfaulted (duplicate OpenMP runtimes).

## ADR-012 Local infrastructure via Docker Compose
Postgres (`pgvector/pgvector:pg17`), Redis, API, worker, beat and frontend run in Docker Compose. A native fallback (Homebrew `postgresql@17` + `brew install pgvector`, which supports pg17/pg18) is documented for running tests without Docker.

## ADR-013 Frontend: client-only SPA, tokens split between memory and storage
Vite + React 19 + TypeScript, Tailwind 4 with shadcn/ui (components copied into the repo, so they can be restyled), TanStack Query for server state, React Router. No SSR: every page sits behind login except the landing page, so server rendering would add a Node server for little gain.

- **Tokens.** The access token (15 min) lives in memory only. The refresh token is in `localStorage`, so a reload keeps you signed in. Trade-off: an XSS bug could read it; an `httpOnly` cookie could not. Moving to a cookie needs the backend to set it (plus CSRF protection), so it is deferred to Milestone 9. Rotation and reuse detection on the server limit the damage of a stolen token.
- **Single-flight refresh.** Parallel requests that hit 401 share one refresh call. Otherwise they would send the same refresh token twice, and reuse detection would revoke the whole session.
- **Hero terrain in raw WebGL**, not three.js: one points draw call and a ~100-line shader don't justify a 600 kB library. The height function exists in GLSL (rendering) and TypeScript (pointer picking), so both are generated from one constants file and a test checks they match.
- **Theme without next-themes.** Its inline `<script>` is for server rendering and triggers a React 19 warning in a client-only app. A 40-line store plus a 1-line script in `index.html` (applies the saved theme before first paint) does the same job.

## ADR-014 Running the whole system: Celery worker, rate limits, one Docker command
**Context.** The app runs on one laptop (cloud free tiers in 2026 offer ~512 MB RAM; the backend needs
1–2 GB for PyTorch and two models). It must start with one command and survive being shared via a link.

- **Background work in Celery, broker = Redis, no result backend.** Résumé parsing (an LLM call, ~5–15 s)
  and evaluation runs used FastAPI `BackgroundTasks`, which run inside the API process: lost on restart,
  and they compete with requests. Outcomes already live in Postgres, so nothing needs Celery results.
  `acks_late` + prefetch 1 + `reject_on_worker_lost` put a task back on the queue if a worker dies;
  tasks are idempotent (résumé processing claims the row atomically).
- **Lost-work safety net.** If Redis is down at upload time, the upload still succeeds and stays
  `pending`; `beat` re-queues anything pending or processing for >10 min. Beat also expires old jobs hourly.
- **Rate limits (fixed window in Redis)** on sign-up and sign-in (per address), and on the assistant,
  résumé uploads and search (per user). Fixed window allows up to 2× the limit across a boundary; fine for
  abuse protection and needs no Lua. **Fails open** if Redis is down: locking everyone out is worse here.
  nginx overwrites `X-Forwarded-For` with the real peer address, so clients can't choose their own "IP".
- **One image for api, worker and beat**; the models are baked in and `HF_HUB_OFFLINE=1` keeps
  containers off the network for models. Runs as a non-root user. Image ≈ 2.5 GB (PyTorch); acceptable
  locally, the first thing to slim (ONNX runtime) if it ever has to fit a small cloud instance.
- **`init` service** runs migrations, then `bootstrap` (idempotent), once per `up`; the API waits for it.
  Only one process migrates, so there are no races.
- **nginx in front, one origin.** No CORS, strict CSP (the one inline script is allowed by hash),
  long-cache hashed assets, no-cache `index.html`. nginx resolves the API through Docker DNS at request
  time, so a recreated API container doesn't break the site.
- **Profiles.** `docker compose up` still starts only Postgres + Redis for development;
  `--profile app` starts everything. The Docker stack uses Redis database 1, so a natively run dev API
  never hands the Docker worker a file it can't see.

**Update (Milestone 9B): sharing.**
- A Cloudflare quick tunnel (`scripts/share.sh`, compose profile `share`) gives a temporary public
  link without accounts or open ports. Chosen over cloud hosting (RAM limits) and over port-forwarding
  (exposes the machine; needs router access).
- Every published port is bound to 127.0.0.1. Before this, Postgres (dev password) and Redis were
  reachable from the local network.
- Through the tunnel every request comes from the cloudflared container, which would put all
  visitors in one rate-limit bucket. nginx takes the visitor address from `CF-Connecting-IP`, trusted
  only from private addresses; with the host port on 127.0.0.1, no one on the network can forge it.
- `SIGNUP_ENABLED=false` closes registration while sharing, so visitors use only the demo account
  (and can't spend the Gemini quota through new accounts).
- The share script checks the link through Cloudflare's resolver (1.1.1.1): asking the system
  resolver for a brand-new name too early makes the OS cache "does not exist" for minutes.
- CI builds both images and smoke-tests the whole stack from an empty database.

