# Talent Intelligence Engine

Intelligent job discovery through retrieval, ranking and agentic AI.

> **Status:** complete (Milestones 0–10). See [PROJECT_STATUS.md](PROJECT_STATUS.md) and [ROADMAP.md](ROADMAP.md)
> (including where the build differs from the plan, and why). To present it: [docs/demo-script.md](docs/demo-script.md)
> and the slide deck in [presentation/](presentation/index.html) (open `presentation/index.html` in a browser).

## What it does
- **Search and ranking:** hybrid retrieval (Postgres full-text + pgvector) and an explainable ranker;
  every result says why it ranks where it does ([docs/retrieval-engine.md](docs/retrieval-engine.md),
  [docs/ranking-engine.md](docs/ranking-engine.md))
- **Personalisation** from stated preferences and from clicks/saves/dismissals, with exploration
- **Résumé intelligence:** PDF → Gemini extraction → grounding checks → you review → profile
  ([docs/resume-intelligence.md](docs/resume-intelligence.md))
- **AI assistant:** LangGraph + Gemini with 10 tools; asks before it changes anything; replies are checked
  against tool output ([docs/agent-architecture.md](docs/agent-architecture.md))
- **Evaluation:** retrieval, ranking (TalentCLEF, human labels), personalisation, assistant, extraction and
  speed, all stored with dataset and commit ([docs/evaluation-framework.md](docs/evaluation-framework.md))
- **Web app:** React + TypeScript; dashboard, search, matches, assistant, résumé, saved jobs, applications,
  preferences, evaluation ([frontend/README.md](frontend/README.md))
- The job listings are **synthetic** and labelled as such ([data/README.md](data/README.md))
- **Security:** threat model, controls, audit results and known gaps in [docs/security.md](docs/security.md)
- **Architecture** as built: [docs/architecture.md](docs/architecture.md); decisions: [docs/engineering-decisions.md](docs/engineering-decisions.md)

## Run it (one command)
Needs Docker (Docker Desktop or OrbStack).

```bash
cp .env.example .env
# In .env: set GEMINI_API_KEY (free: https://aistudio.google.com/apikey), and generate the two secrets:
python3 -c "import secrets; print('JWT_SECRET=' + secrets.token_urlsafe(48))" >> .env
python3 -c "import secrets; print('DEMO_PASSWORD=demo-' + secrets.token_urlsafe(9))" >> .env

docker compose --profile app up -d --build
```
Open **http://localhost:8090** and sign in as `demo@example.com` with your `DEMO_PASSWORD`
(a fictional profile with ready-made matches), or create your own account.

The first build takes a few minutes (the backend image includes PyTorch and the two models, about
2.5 GB). Later starts take seconds. What starts:

| Service | Role |
|---|---|
| `postgres`, `redis` | Database (with pgvector) and the task queue / rate-limit counters |
| `init` | Runs once per start: migrations, then `bootstrap` (skills, jobs, embeddings, demo account; skips work already done) |
| `api` | FastAPI on the internal network |
| `worker` | Celery: résumé parsing and evaluation runs |
| `beat` | Schedules: expire old jobs hourly, re-queue stuck résumés every 5 min |
| `web` | nginx: the built frontend, and a proxy for `/api` (one origin, no CORS) |

Stop with `docker compose --profile app down` (data is kept in Docker volumes).
Without an API key the app still works; résumé parsing and the assistant say they're unavailable.

## Share a link (while your laptop is on)
```bash
scripts/share.sh          # starts the app if needed, prints a https://….trycloudflare.com link
scripts/share.sh url      # show the link again
scripts/share.sh stop     # close it; the app keeps running locally
```
A free Cloudflare quick tunnel (no account). The link works only while this machine and Docker
are running, and changes each time the tunnel restarts. Rate limits stay on; set
`SIGNUP_ENABLED=false` in `.env` to let visitors use only the demo account. The site is otherwise
reachable only from this machine (ports are bound to 127.0.0.1).

## Develop
For working on the code, run only the database and Redis in Docker and the rest natively:

```bash
docker compose up -d                 # Postgres on :5433, Redis on :6380
cd backend
uv sync                              # creates .venv from the lockfile (installs Python 3.13)
uv run alembic upgrade head
uv run python -m app.cli bootstrap   # skills, synthetic jobs, embeddings (+ demo if DEMO_PASSWORD is set)
uv run uvicorn app.main:app --reload --port 8080      # API docs: http://localhost:8080/docs
uv run celery -A app.worker.celery_app worker -l INFO # in another terminal: résumé parsing
cd ../frontend && npm install && npm run dev           # http://127.0.0.1:5180
```
Needs [uv](https://docs.astral.sh/uv/) and Node 24.

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
