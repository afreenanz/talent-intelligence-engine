# Project Status

_Last updated: 2026-11-17_

**Current milestone:** 6A: AI agent, **approved and merged** (PR #6)
**Next:** 6B: agent hardening (streaming optional, more failure tests), then Milestone 7: evaluation

## Milestone 6A: AI agent (verified 2026-11-18)
- [x] Gemini tool calling (stateless Interactions API, parallel calls), verified live before building
- [x] 10 tools with Pydantic I/O over the real services; identity from auth, never from the LLM
- [x] LangGraph graph: agent → tools → confirm (interrupt) → ground → fail_safe; Postgres checkpointer in its own schema
- [x] Confirmation before save/preference changes; decline path; pending-action lock
- [x] Deterministic grounding check with one corrective retry; step limit
- [x] conversations/messages tables (migration a68d84800899), chat/confirm/list/get/delete API
- [x] Live end-to-end run with both brief examples, plus cross-session memory
- [x] Bugs found: message ordering by transaction timestamp (fixed with `seq`), unclosed pool (lifespan close)
- [x] 301 tests (17 agent tests with a scripted LLM); ruff, mypy --strict, alembic check clean

## Milestone 5B: Personalization engine (verified 2026-11-18)
- [x] Deterministic role-category classifier (title rules + skill fallback)
- [x] Derived preferences from events (confirmed clicks only, no negative impressions, decay, support thresholds, confidence < 1), recomputed on each action
- [x] Bounded adjustment (±0.1), explicit-over-derived precedence, explicit prefs override profile facts; explanations say "you prefer" vs "based on your activity"
- [x] Preference retrieval channel + exploration slots (added after the v1 experiment exposed a feedback loop and a retrieval ceiling)
- [x] Persona experiment v1 → v2: learned +0.091 → +0.240 NDCG@10; explicit +0.341 → +0.410 (simulated, synthetic)
- [x] `personalize` flag on search and recommendations; 284 tests; ruff, mypy --strict clean

## Milestone 5A: Activity & explicit preferences (verified 2026-11-18)
- [x] Migration `dbd166f11fd2`: search_logs, job_interactions, saved_jobs, applications, agent_memory
- [x] Search/recommendations log each search plus one impression per result (positions); `search_log_id` returned
- [x] Feedback (click/dismiss) with ownership-checked search attribution
- [x] Saved jobs (idempotent; state + event in one transaction; keyset pagination)
- [x] Applications with a status state machine (409 + allowed transitions on invalid moves)
- [x] Explicit preferences: fixed validated vocabulary, upsert returns previous value, delete; 422 (not 500) on bad values
- [x] Recent searches endpoint
- [x] 259 tests; ruff, mypy --strict, alembic check clean
- [x] Approved (2026-11-18)

## Milestone 4B: Ranking evaluation on real labels (verified 2026-11-18)
- [x] Checksum-pinned TalentCLEF fetch (MD5 matches Zenodo), safe extraction, git-ignored, CC BY attribution
- [x] Deterministic job/CV parsing (skills from each job's own list, experience from the experience section only)
- [x] Comparison with production code paths: lexical / dense / hybrid / + features / + cross-encoder / ablations, MAP added
- [x] Exploratory LambdaMART (leave-one-query-out) in an isolated process (torch + LightGBM OpenMP crash on macOS reproduced and fixed)
- [x] Findings: features +0.040 MAP ✱, features + cross-encoder +0.067 MAP ✱; lexical hurts hybrid on long queries (hypothesis, not tuned)
- [x] 243 tests; ruff, mypy --strict clean
- [x] Approved and merged (PR #4)

## Milestone 4A: Ranking engine (verified 2026-11-17)
- [x] 10 candidate-job features with explicit neutral handling of missing data (unit-tested policy per feature)
- [x] Transparent weighted ranker (`weights_v1.json`, validated) with per-feature contributions
- [x] Cross-encoder stage (ms-marco-MiniLM-L6-v2) on the top 50; sigmoid blending (min-max rejected after a live failure)
- [x] Feature-derived explanations; `ranking` option on search; `GET /api/v1/recommendations`
- [x] Live run with real models: profile fit drives order; cross-encoder adds ≈0.4–0.6 s
- [x] 235 tests; ruff, mypy --strict clean
- [x] Approved and merged (PR #3)

## Milestone 3B: Retrieval evaluation (verified 2026-11-17)
- [x] Metrics: P@K, R@K, MRR, NDCG@K (graded) with hand-computed unit tests
- [x] `evaluation_runs` table (migration `5340709bcd09`); every run stores config, metrics, per-query scores, git commit
- [x] Dataset `retrieval_v1`: 40 queries in 7 categories, dev/test split, 12,998 silver judgments from generator ground truth
- [x] Runner: dev-only fusion tuning, held-out evaluation, paired bootstrap CIs, per-category breakdown, latency; Markdown reports
- [x] Findings: lexical weakest on both splits (abbreviations); hybrid ≥ lexical; **model choice and fusion tuning not decidable** (ranking flips between splits)
- [x] Real-dataset options with licences checked (TalentCLEF 2026 CC BY 4.0; data_jobs Apache-2.0)
- [x] 205 tests; ruff, mypy --strict, alembic check clean
- [x] Approved and merged (PR #2)

## Milestone 3A: Retrieval engine (verified 2026-11-17)
- [x] Migration `3dcced24e94a`: job_embeddings, candidate_embeddings, jobs.skills_text (backfilled), generated weighted search_vector + GIN
- [x] Embedding service (Sentence Transformers, bge-small-en-v1.5, explicit query prefix), incremental `embed-jobs` (1,593 in ~30 s; re-run 0.11 s)
- [x] Lexical (FTS, OR semantics, weighted), dense (pgvector cosine), hybrid (RRF) behind one `retrieve_jobs`
- [x] Profile/recommendation mode with cached candidate embeddings; cold-start handling
- [x] `POST /api/v1/jobs/search` with ranks, scores and per-stage timings
- [x] CPU-only torch on Linux; HF model cache in CI
- [x] 193 tests (incl. 3 against the real model); ruff, mypy --strict, alembic check clean
- [x] Approved and merged to main (2026-11-17)

## Milestone 2B: Resume intelligence (verified 2026-11-17)
- [x] LLM provider interface + Gemini adapter (REST Interactions API, retries, schema adaptation)
- [x] Gemini key configured; model choice measured (3.5 Flash-Lite ≈ 7 s; 3.8 Flash timed out)
- [x] PDF upload (magic-byte check, 5 MB limit, UUID paths, 0600 files), text extraction + cleaning
- [x] Versioned extraction prompt; Pydantic-validated structured output
- [x] Grounding: ungrounded skills dropped, name/location dropped, employers flagged; experience computed from dates
- [x] Review → apply flow (skills merged with source=resume); reprocess; delete (row + file)
- [x] Live end-to-end run against Gemini with a fictional resume: parsed correctly, 5.5 y computed, alias resolution, no warnings
- [x] 170 tests (no test ever calls the real LLM), 90% coverage; ruff, mypy --strict, alembic check clean
- [x] Approved and merged to main (2026-11-17)
- Deferred: extraction-quality benchmark on labelled resumes (Milestone 7); Celery worker (Milestone 9); OCR (out of scope)


## Milestone 2A: Job ingestion (verified 2026-11-17)
- [x] Migration `265b9963294b`: jobs, job_skills, ingestion_runs, ingestion_errors, skills.is_ambiguous
- [x] Curated skill taxonomy (138 skills, 92 aliases) + idempotent `seed-skills`
- [x] CSV / JSON / JSONL streaming readers; `JobRecordIn` validation contract
- [x] Normalization: HTML cleaning, salary (LPA/lakh/crore/k, monthly/hourly → annual), experience, city/country/remote, title & company keys
- [x] Skill identification: explicit lists via aliases + conservative dictionary matching in text
- [x] Idempotent incremental ingestion (re-import = 2,080 unchanged, 0 writes)
- [x] Near-duplicate detection with lifetime rule: 80/80 injected duplicates, 0 false positives (synthetic, see docs/ingestion.md caveat)
- [x] Expiry, snapshot mode with safety valve, failed-record storage + retry
- [x] Synthetic dataset generator (deterministic, labelled, with injected ground truth)
- [x] `GET /api/v1/jobs` (keyset pagination, filters) and `GET /api/v1/jobs/{id}`
- [x] 133 tests passing; ruff, mypy --strict and `alembic check` clean
- [x] Approved and merged to main (2026-11-17)
- Not yet: scheduled ingestion (Celery beat → Milestone 9), external job API adapter (needs a provider with usable terms; interface planned for Milestone 9)


## Milestone 1: Backend foundation (verified 2026-11-17)
- [x] Docker Compose: Postgres 17.12 + pgvector 0.8.7, Redis 8.2, both healthy
- [x] FastAPI app: config, structured logging, request IDs, error envelope, CORS
- [x] SQLAlchemy 2.1 models + Alembic migration; upgrade → downgrade → upgrade verified; `alembic check` clean
- [x] Auth: register / login / refresh (rotation + reuse detection) / logout
- [x] Candidate profile `GET`/`PUT /me` with skill normalization and alias resolution
- [x] Health: live + ready (DB + Redis)
- [x] 52 tests passing, 95% line coverage; ruff + mypy --strict clean
- [x] GitHub Actions CI: first run green on GitHub (private repo afreenanz/talent-intelligence-engine)
- [x] Committed and pushed (bbc5164)

Deferred deliberately (in the roadmap):
- Rate limiting on auth endpoints → Milestone 9 (needs the Redis limiter; noted as an enumeration mitigation)
- Curated skill taxonomy + aliases seed → Milestone 2
- Known warning: Starlette deprecates `httpx` for its TestClient in favour of `httpx2`. Harmless; revisit when upgrading deps.

## Milestone 0: Research & architecture (approved 2026-11-17)
- [x] Environment inspection, version checks, docs research, architecture/schema/ADRs

## Blocked / needs you
| Item | Why | Action |
|---|---|---|
| ~~Docker~~ ✅ | OrbStack installed; Docker 29.8.2, Compose v5.5.0; `hello-world` ran (2026-11-17) | done |
| ~~Python 3.13~~ ✅ | uv 0.13.8 + CPython 3.13.18, SSL verified (2026-11-17) | done |
| pgvector not installed (native) | Only needed for the no-Docker fallback | `brew install pgvector` (optional) |
| Gemini API key (free tier) | Resume extraction and agent (Milestones 2, 6) | **Decided: Gemini free tier** (2026-11-17); OpenRouter is the alternative via the OpenAI-compatible adapter. Create the key in Google AI Studio before Milestone 2. It goes into `.env` only |

## Environment (inspected 2026-11-17)
| Tool | Found | Notes |
|---|---|---|
| macOS | Darwin 25.4, Apple M5, 16 GB RAM | CPU/MPS inference is fine for small models |
| Python | 3.14.5 (python.org, SSL certificates not installed), 3.11.16 (Homebrew) | Run `Install Certificates.command` if you keep using 3.14 |
| Node / npm | 26.0.0 / 11.12.1 | OK for Vite 8 / React 19 |
| PostgreSQL | 17.11 (Homebrew), **not running**, no pgvector | |
| Redis | 8.10.3, running | |
| Docker | **not installed** | |
| Git | 2.50.1 | |

## Verified current versions (PyPI/npm, 2026-11-17)
FastAPI 0.163 · Pydantic 2.14 · SQLAlchemy 2.1 · Alembic 1.20 · psycopg 3.3 · pgvector-python 0.5 ·
sentence-transformers 6.3 · torch 2.15 · LangGraph 1.2 · langgraph-checkpoint-postgres 3.2 ·
scikit-learn 1.9 · LightGBM 4.7 · Celery 5.7 · pgvector (ext) 0.8.7 · React 19.3 · Vite 8.3 ·
TypeScript 7.0 · Tailwind 4.3 · TanStack Query 5 · React Router 8 · Recharts 3.10.
Exact versions are pinned in Milestone 1. Releases from the last two weeks get one patch release of buffer.
