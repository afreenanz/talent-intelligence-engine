# Contributing

## Workflow
- Branch from `main`: `feat/<area>-<short-desc>`, `fix/...`, `docs/...`, `chore/...`
- Commit messages: [Conventional Commits](https://www.conventionalcommits.org/) (`feat(auth): add refresh rotation`)
- Every change keeps `main` green: lint, types, migration check and tests must pass.

## Code conventions
- Layers per domain: `router` (HTTP) → `service` (business logic, owns commits) → `repository` (SQL).
  Services never import FastAPI; routers never write queries.
- Raise domain errors from `app/core/errors.py`, not `HTTPException`.
- Candidate-owned data is always looked up via the authenticated user, never via an ID from the client.
- Type hints everywhere; `mypy --strict` must pass for `app/`.

## Schema changes
1. Edit the models.
2. `uv run alembic revision --autogenerate -m "<what>"`
3. **Read and fix the generated file.** Autogenerate misses things such as ENUM drops and extensions.
4. `uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head`
5. `uv run alembic check` must report no changes.

## Dependencies
`pyproject.toml` sets `exclude-newer` so releases from the last ~2 weeks are ignored.
To upgrade, bump that date deliberately, run `uv lock --upgrade`, and run the full test suite.

## Data
Never commit `.env`, real resumes, or datasets containing personal information.
Synthetic data must be labelled as synthetic.
