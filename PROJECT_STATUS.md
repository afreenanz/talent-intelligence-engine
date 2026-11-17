# Project Status

_Last updated: 2026-11-17_

**Current milestone:** 0: Research & architecture, **awaiting approval**

## Completed
- [x] Environment inspection (see "Environment" below)
- [x] Library version and compatibility check against PyPI/npm (2026-11-17)
- [x] Docs checked: pgvector README, LangGraph persistence/interrupts/memory, PostgreSQL text-search ranking, Sentence-Transformers cross-encoders
- [x] Project-level Git repository initialised (previously the folder was inside a repo rooted at the home directory)
- [x] Draft docs: architecture, database design, ADRs, retrieval, ranking/personalization, agent, memory, evaluation

## Pending (Milestone 0)
- [ ] Your review of the architecture, schema and ADRs
- [ ] Decisions needed from you (see below)
- [ ] First commit (after approval)

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
