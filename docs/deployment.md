# Deployment and operations

> Status: **As built (Milestone 9, runbook verified after Milestone 10).** The app runs on one machine
> with Docker. Why not a cloud host: 2026 free tiers offer about 512 MB RAM and the backend needs 1–2 GB
> for PyTorch and two models (ADR-014). Sharing goes through a temporary tunnel.

## Requirements
- Docker (Docker Desktop or OrbStack), about 4 GB free disk for images, 2–3 GB RAM while running.
- A `.env` file (copy `.env.example`). Required for the Docker stack: `JWT_SECRET`. Recommended:
  `GEMINI_API_KEY` (assistant and résumé parsing; without it those features say they're unavailable)
  and `DEMO_PASSWORD` (creates the demo account).

## Start, stop, update

```bash
docker compose --profile app up -d --build     # first time: builds images (a few minutes)
docker compose --profile app up -d             # later starts: seconds
docker compose --profile app ps                # status and health
docker compose --profile app down              # stop (data is kept in volumes)
```
Open **http://localhost:8090**. API docs: http://localhost:8090/docs.

**Update to a new version:** `git pull`, then `docker compose --profile app up -d --build`. The `init`
service applies any new migrations before the API starts. Back up first (below) if the update includes a migration.

`docker compose up -d` without `--profile app` starts only Postgres and Redis, for running the code natively
(see the README's "Develop" section).

## What runs

| Service | Image | Role | Restarts |
|---|---|---|---|
| `postgres` | `pgvector/pgvector:0.8.7-pg17-trixie` | Database (+ pgvector), volume `pgdata` | always healthy-checked |
| `redis` | `redis:8.2-alpine` (AOF on) | Task queue (db 1 for the Docker stack), rate-limit counters, volume `redisdata` | |
| `init` | `talent-engine-backend` | Once per `up`: `alembic upgrade head`, then `app.cli bootstrap` (skills, jobs, embeddings, demo account; skips work already done) | no |
| `api` | `talent-engine-backend` | FastAPI on the internal network (`--proxy-headers`) | unless-stopped |
| `worker` | `talent-engine-backend` | Celery: résumé parsing, evaluation runs (concurrency 2) | unless-stopped |
| `beat` | `talent-engine-backend` | Schedules: expire jobs hourly (minute 5); re-queue stuck résumés every 5 min | unless-stopped |
| `web` | `talent-engine-web` (nginx 1.29) | Built frontend + `/api` proxy, security headers; the only published port | unless-stopped |
| `tunnel` (profile `share`) | `cloudflare/cloudflared:2026.10.7` | Public quick-tunnel link | unless-stopped |

Start order is enforced: Postgres healthy → `init` completes → API healthy → web. Uploaded résumés live in
volume `uploads`, shared by `api` (writes) and `worker` (reads).

**Images:** backend ≈ 2.6 GB (CPU-only PyTorch + the embedding and cross-encoder models baked in; runs as
uid 10001; `HF_HUB_OFFLINE=1`, so no model downloads at runtime). Web ≈ 94 MB.

## Configuration
Every setting is an environment variable read by `app/core/config.py`; `.env.example` lists them all with
comments. The Docker stack overrides the connection settings itself (`DATABASE_URL`, `REDIS_URL`,
`UPLOAD_DIR`) and runs with `ENVIRONMENT=production`, which refuses to start with a missing or weak `JWT_SECRET`.

| Variable | Default | Notes |
|---|---|---|
| `JWT_SECRET` | none | Required. `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `GEMINI_API_KEY` | empty | Free key at aistudio.google.com/apikey. Free-tier prompts may be used by Google |
| `LLM_MODEL` | `gemini-3.5-flash-lite` | |
| `DEMO_PASSWORD` | unset | Unset = no demo account |
| `RATE_LIMITS_ENABLED` | `true` | |
| `SIGNUP_ENABLED` | `true` | Set `false` while sharing a public link |
| `WEB_HOST_PORT` | `8090` | Bound to 127.0.0.1 |
| `POSTGRES_HOST_PORT` / `REDIS_HOST_PORT` | `5433` / `6380` | Bound to 127.0.0.1; for native development only |
| `ACCESS_TOKEN_TTL_MINUTES` / `REFRESH_TOKEN_TTL_DAYS` | `15` / `14` | |
| `MAX_RESUME_BYTES` | 5 MB | |

## Sharing a link
```bash
scripts/share.sh          # starts the app if needed and prints https://<random>.trycloudflare.com
scripts/share.sh url      # show it again
scripts/share.sh stop     # close it
```
The link works only while this machine and Docker run, and changes each time the tunnel restarts. Through the
tunnel, nginx uses Cloudflare's `CF-Connecting-IP` as the visitor's address (trusted only from private
addresses), so rate limits apply per visitor. Consider `SIGNUP_ENABLED=false` so visitors use only the demo account.

## Backups and restore
Verified end to end on a throwaway copy of the stack: a user created before the backup could sign in
after a full wipe and restore, with job counts and uploaded files intact.

```bash
scripts/backup.sh                         # -> backups/<UTC timestamp>/db.dump + uploads.tgz
scripts/restore.sh backups/<timestamp>    # asks you to type 'restore'; REPLACES current data
```
- `db.dump` is a `pg_dump` custom-format archive of the whole database (app tables and the LangGraph
  schema); `uploads.tgz` holds the résumé PDFs.
- Restore stops the app (the database stays up), runs `pg_restore --clean --if-exists`, replaces uploads,
  fixes their ownership, and starts the app; migrations then no-op.
- Backups contain personal data (profiles, résumés, conversations). `backups/` is git-ignored; keep it private.
- Redis needs no backup: it holds only queued tasks (lost tasks are re-queued by `beat`) and rate-limit counters.

## Logs and health
```bash
docker compose --profile app logs -f api worker     # follow (JSON lines with request_id)
curl -s http://localhost:8090/health/ready          # {"status":"ok","checks":{"database":"ok","redis":"ok"}}
docker compose --profile app exec worker celery -A app.worker.celery_app inspect ping
```
Logs are capped at 3 × 10 MB per service. Each API response carries `X-Request-ID`; search the logs for it
to follow one request.

## Admin tasks
```bash
docker compose --profile app exec api python -m app.cli make-admin you@example.com
docker compose --profile app exec api python -m app.cli seed-demo          # reset the demo account
docker compose --profile app exec api python -m app.cli expire-jobs
docker compose --profile app exec api python -m app.cli runs               # recent ingestion runs
```

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| `init` exits with an error | `docker compose --profile app logs init`. A migration error usually means the database is from a newer branch; restore a backup or downgrade from that branch |
| API not healthy, logs say `JWT_SECRET` | Set a 32+ character `JWT_SECRET` in `.env` |
| Résumé stuck on "Reading…" | Worker logs. No `GEMINI_API_KEY` means parsing is unavailable; a stuck job is re-queued within 10 minutes |
| Assistant says it's busy | Gemini free-tier rate limit; wait a minute |
| "Too many sign-in attempts" | Rate limit; wait, or clear counters: `docker compose exec -T redis redis-cli -n 1 --scan --pattern 'rl:*' \| xargs docker compose exec -T redis redis-cli -n 1 del` |
| Port 8090 already in use | Set `WEB_HOST_PORT` in `.env` |
| Share link doesn't open | `scripts/share.sh stop && scripts/share.sh` for a fresh one |

## CI
Every push and PR runs: backend (ruff, mypy strict, `alembic check`, API reference up to date, pytest against
Postgres + Redis), frontend (typecheck, oxlint, tests, build) and **stack** (build both images, start the full
stack on an empty database, then smoke-test health, stats, demo sign-in, ranked recommendations, SPA routing,
the CSP header and the worker).
