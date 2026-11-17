# Changelog

Format based on [Keep a Changelog](https://keepachangelog.com/). Each entry corresponds to a milestone.

## [Unreleased]

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
