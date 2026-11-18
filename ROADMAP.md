# Roadmap

Each milestone ends with a **review gate**. Work stops, the results are presented, and the next
milestone starts only after approval. A milestone counts as done only when its exit criteria are verified
by commands you can run yourself.

| # | Milestone | Exit criteria (verified, not just "code written") |
|---|---|---|
| 0 | Research & architecture | Environment inspected, stack verified, architecture/schema/ADRs documented, plan approved |
| 1 | Backend foundation | `docker compose up` gives Postgres+pgvector and Redis; FastAPI health endpoints; Alembic migration for users/profiles/skills; register/login/me with JWT + refresh; ownership tests; ruff + mypy + pytest green in CI |
| 2 | Resume & job ingestion | PDF upload → extraction → reviewable parsed profile; CSV/JSON job import that is idempotent (re-import = 0 changes), dedups, handles expiry, records failed rows; labelled synthetic dataset |
| 3 | Retrieval engine | Embeddings stored with content hash; lexical, dense and hybrid (RRF) retrieval behind `retrieve_jobs`; metric functions unit-tested; first eval set + real comparison report |
| 4 | Ranking engine | Feature pipeline, weighted baseline, cross-encoder stage, LTR experiment (or a documented "insufficient data"); ranking report |
| 5 | Personalization | Interaction logging (incl. impressions), explicit + derived preferences, capped adjustment, cold-start handling, persona-based experiment |
| 6 | Agent | LangGraph graph with 10 tools, Pydantic validation, confirmation interrupts, Postgres checkpointing, persisted conversations, grounding check, tests with a scripted fake LLM |
| 7 | Evaluation | Extraction, agent and response-quality benchmarks; `evaluation_runs` populated by scripts; reports generated |
| 8 | Frontend | All 13 pages against real APIs; component + flow tests |
| 9 | Infrastructure | Redis caching with invalidation + benchmarks, Celery beat schedules, production compose, CI, deployment procedure |
| 10 | Final review | Security audit, performance review, docs complete, demo script |

Estimated order of risk (highest first): evaluation data quality → personalization evidence → agent reliability → everything else.

## Outcome (Milestone 10, 2026-11-19)

All milestones closed through review gates (PRs #1–#13). Where the build differs from the plan above:

| # | Delivered | Changed from plan, and why |
|---|---|---|
| 1–2 | As planned | |
| 3 | As planned | The "best" embedding model flipped between dev and test splits; kept bge-small and reported the instability instead of picking a winner |
| 4 | Features, weighted baseline, cross-encoder, LTR experiment | LambdaMART was exploratory only: 10 labelled queries is below the data gate in ADR-011 |
| 5 | As planned, plus a v2 | v1 created a feedback loop (measured); v2 added a preference retrieval channel and exploration slots |
| 6 | As planned | Only the Gemini adapter; the provider interface stays for others |
| 7 | As planned | |
| 8 | 13 pages against real APIs; component and flow tests | |
| 9 | Celery worker + beat, rate limits, one-command Docker stack, CI image build + smoke test, share link | **No Redis cache:** measured search at ~60 ms with ~8 ms cacheable (see performance-benchmarks.md). **No cloud deployment:** 2026 free tiers offer ~512 MB RAM, the backend needs 1–2 GB; sharing uses a Cloudflare quick tunnel instead |
| 10 | Security audit, performance re-measure, docs, demo script, interview prep | |
