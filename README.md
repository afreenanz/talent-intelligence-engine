# Talent Intelligence Engine

Intelligent job discovery through retrieval, ranking and agentic AI.

> **Status:** Milestones 1 and 2 (backend foundation, job ingestion, resume intelligence) are complete.
> Retrieval, ranking, the agent and the frontend are not built yet. See [ROADMAP.md](ROADMAP.md) and [PROJECT_STATUS.md](PROJECT_STATUS.md).

## What works today
- PostgreSQL 17 + pgvector and Redis via Docker Compose
- FastAPI app with structured logging, request IDs and a consistent JSON error envelope
- Alembic migrations: users, refresh tokens, candidate profiles, skills, skill aliases
- Auth: register, login (Argon2id), short-lived JWT access tokens, rotating refresh tokens with reuse detection, logout
- Candidate profile: `GET`/`PUT /api/v1/candidates/me`, with skill normalization against a shared vocabulary
- Health: `/health/live`, `/health/ready` (checks DB + Redis)
- Job ingestion from CSV/JSON/JSONL: normalization, skill extraction, idempotent upserts,
  near-duplicate detection, expiry, retry of failed records ([docs/ingestion.md](docs/ingestion.md))
- `GET /api/v1/jobs` (cursor pagination, filters) and `GET /api/v1/jobs/{id}`
- A labelled **synthetic** job dataset ([data/README.md](data/README.md))
- Resume upload → PDF text → Gemini structured extraction → grounding checks → candidate review → profile
  ([docs/resume-intelligence.md](docs/resume-intelligence.md))
- 170 tests (unit, integration, API; none call a real LLM) against a real Postgres database; ruff, mypy (strict) and a migration drift check in CI

## Prerequisites
- Docker (Docker Desktop or OrbStack)
- [uv](https://docs.astral.sh/uv/) (`brew install uv`). It installs Python 3.13 automatically.

## Run locally
```bash
cp .env.example .env                 # then set GEMINI_API_KEY for resume parsing
docker compose up -d                 # Postgres on :5433, Redis on :6380
cd backend
uv sync                              # creates .venv from the lockfile
uv run alembic upgrade head          # apply migrations
uv run uvicorn app.main:app --reload --port 8080
```
Open the interactive API docs at http://localhost:8080/docs.

Load the skill taxonomy and the synthetic jobs (from `backend/`):
```bash
uv run python -m app.cli seed-skills
uv run python -m app.cli ingest-jobs ../data/synthetic/jobs_v1.jsonl --source synthetic_v1
```

## Test and check
```bash
cd backend
uv run pytest --cov                  # needs `docker compose up -d` (uses database tie_test)
uv run ruff check . && uv run ruff format --check .
uv run mypy app
uv run alembic check                 # fails if models and migrations have drifted apart
```

## Try it with curl
```bash
B=http://localhost:8080/api/v1
curl -s -X POST $B/auth/register -H 'content-type: application/json' \
  -d '{"email":"me@example.com","password":"a-long-password"}'
TOKEN=$(curl -s -X POST $B/auth/login -H 'content-type: application/json' \
  -d '{"email":"me@example.com","password":"a-long-password"}' | python3 -c 'import json,sys;print(json.load(sys.stdin)["access_token"])')
curl -s $B/candidates/me -H "Authorization: Bearer $TOKEN"
```

## Repository layout
```
backend/   FastAPI app (app/), Alembic migrations, tests
docs/      architecture, database design, ADRs, module designs
infra/     Postgres init script (creates the test database)
```
Design docs: [architecture](docs/architecture.md) · [database](docs/database-design.md) ·
[decisions](docs/engineering-decisions.md) · [retrieval](docs/retrieval-engine.md) ·
[ranking](docs/ranking-engine.md) · [agent](docs/agent-architecture.md) ·
[memory](docs/memory-design.md) · [evaluation](docs/evaluation-framework.md)
