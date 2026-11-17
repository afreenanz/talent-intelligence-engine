# Changelog

Format based on [Keep a Changelog](https://keepachangelog.com/). Each entry corresponds to a milestone.

## [Unreleased]

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
