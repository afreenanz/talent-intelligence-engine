# Changelog

Format based on [Keep a Changelog](https://keepachangelog.com/). Each entry corresponds to a milestone.

## [Unreleased]

### Milestone 9A: One-command stack
- Docker images for backend (api/worker/beat) and web (nginx); `--profile app` runs everything at :8090
- Celery worker + beat replace in-process background tasks; stale résumé requeue; hourly job expiry
- Rate limits with 429 + Retry-After; demo account; `bootstrap` and `seed-demo` CLI commands

### Milestone 8C: Assistant, résumé, dashboard, evaluation
- Assistant page with confirmations, step trace and safe reply rendering
- Résumé upload, review and apply; dashboard; admin evaluation page
- Fixes: fractional number inputs no longer block forms; phone users can sign out

### Milestone 8B: Jobs UI
- Search, job detail with match breakdown, For you (beam on the top match), saved jobs, applications, preferences
- Click and dismiss feedback from the UI; application status moves mirror the backend's allowed transitions
- Backend: `SearchHit.job` (display fields) attached in one query
- Lazy-loaded app routes

### Milestone 8A: Frontend foundation
- `frontend/`: Vite + React + TypeScript app with design tokens, landing page (WebGL terrain hero), sign in/up, app shell
- Typed API client with single-flight token refresh; auth context and route guards
- Backend: `GET /api/v1/auth/me`, public `GET /api/v1/stats`
- CI: frontend job (typecheck, lint, test, build)

### Milestone 7B: Performance and evaluation API
- `bench-performance` (latency, throughput, query plans, exact vs HNSW); `make-admin` CLI
- Admin evaluation API: `GET /api/v1/evaluations`, `GET /{id}`, `POST /run` (retrieval only)
- Generated API reference; performance benchmark doc

### Milestone 7A: LLM-quality benchmarks
- `eval-agent` (agent_v1, 23 cases) and `eval-extraction` (extraction_v1, 10 resumes) with deterministic scoring
- Gemini adapter: Retry-After / 429 backoff, client-side pacing, thinking tokens billed as output
- Resume post-processing: negation filter; dictionary-only skills become suggestions

### Milestone 6A: AI agent
- Gemini tool-calling adapter (stateless Interactions API, parallel calls)
- 10 validated tools; LangGraph graph with confirmation interrupts, grounding check, step limit
- Postgres checkpointer in a separate schema; conversations/messages tables (migration `a68d84800899`)
- `/api/v1/agent/chat`, `/confirm`, conversation list/get/delete

### Milestone 5B: Personalization engine
- Role-category classifier; derived preferences from the event log with explicit evidence rules
- Bounded personalization adjustment with explanations; explicit preferences override profile facts
- Preference-aware retrieval channel and exploration slots in recommendations
- `eval-personalization` simulated-persona experiment (v1 and v2 reports)

### Milestone 5A: Activity and explicit preferences
- search_logs / job_interactions / saved_jobs / applications / agent_memory (migration `dbd166f11fd2`)
- Server-side impression logging; click/dismiss feedback; recent searches
- Saved-jobs and applications APIs (state machine); explicit preference memory API

### Milestone 4B: Ranking evaluation (TalentCLEF 2026)
- Checksum-verified dataset fetch; deterministic job/CV parsing
- `eval-ranking` CLI comparing retrieval and ranking stages on human labels, with bootstrap CIs
- MAP metric; `skills_known` feature flag; exploratory LambdaMART in an isolated process

### Milestone 4A: Ranking engine
- Candidate-job feature pipeline, weighted ranker with versioned weights, explanations
- Cross-encoder re-ranking stage (top 50) with calibrated sigmoid blending
- `ranking` option on `POST /api/v1/jobs/search`; new `GET /api/v1/recommendations`

### Milestone 3B: Retrieval evaluation
- Ranking metrics with hand-computed tests; `evaluation_runs` table
- `retrieval_v1` silver benchmark (40 queries, dev/test) and qrels builder from generator ground truth
- `eval-retrieval` CLI: tuning on dev, held-out comparison, paired bootstrap CIs, Markdown reports
- Synthetic jobs now carry a `truth` field (ignored by ingestion)

### Milestone 3A: Retrieval engine
- Embedding tables and generated full-text search vector (migration `3dcced24e94a`)
- Sentence Transformers embedder with explicit query prompts; incremental job embedding CLI
- Lexical, dense and RRF hybrid retrieval with shared SQL filters; profile-based retrieval
- `POST /api/v1/jobs/search`

### Milestone 2B: Resume intelligence
- LLM provider protocol; Gemini adapter over the REST Interactions API with retries and schema adaptation
- Resume upload/list/get/reprocess/apply/delete endpoints with ownership checks
- PDF text extraction (pypdf) with clear failure reasons; versioned extraction prompt
- Deterministic post-processing: skill grounding, computed experience, warnings, provenance
- `resumes` table (migration `f244ee3f984c`)

### Milestone 2A: Job ingestion
- Jobs schema (jobs, job_skills, ingestion_runs, ingestion_errors) with integrity constraints
- Curated skill taxonomy v1 and idempotent seeding
- CSV/JSON/JSONL ingestion: validation, normalization, skill extraction, content hashing,
  idempotent upserts, near-duplicate linking, expiry, snapshot mode, retry of failed records
- Deterministic synthetic job dataset (2,084 records) with injected ground truth
- `GET /api/v1/jobs` (cursor pagination + filters), `GET /api/v1/jobs/{id}`
- CLI: `seed-skills`, `ingest-jobs`, `runs`, `retry-failed`, `expire-jobs`

### Milestone 1: Backend foundation
- Docker Compose: `pgvector/pgvector:0.8.7-pg17-trixie` and `redis:8.2-alpine` with health checks and volumes
- FastAPI app factory, structlog logging, request-ID middleware, JSON error envelope
- Settings via pydantic-settings; weak or missing JWT secrets are refused
- Alembic migration `f395728ae912`: extensions (citext, pg_trgm, vector), users, refresh_tokens,
  candidate_profiles, skills, skill_aliases, candidate_skills
- Auth endpoints: register, login, refresh (rotation + reuse detection), logout
- Candidate endpoints: `GET`/`PUT /api/v1/candidates/me`
- Health endpoints: `/health/live`, `/health/ready`
- 52 tests (unit + API against real Postgres), GitHub Actions CI

### Milestone 0: Research & architecture
- Architecture, database design, ADRs, and design docs for retrieval, ranking, agent, memory and evaluation
