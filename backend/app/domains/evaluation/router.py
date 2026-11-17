"""Admin-only access to evaluation results (the dashboard reads only from here).

Only the retrieval experiment can be triggered over HTTP: it costs nothing and takes ~1 min.
Experiments that call the LLM (agent, extraction) stay CLI-only, so a click can't spend quota.
"""

import uuid
from collections.abc import Callable
from typing import Annotated, Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.api.deps import CurrentAdmin, DbSession
from app.core.errors import NotFoundError
from app.domains.evaluation.models import EvaluationRun

router = APIRouter(prefix="/evaluations", tags=["evaluations"])
HEAVY_KEYS = {"per_query", "cases", "per_resume", "per_run"}


class EvaluationSummary(BaseModel):
    id: uuid.UUID
    experiment_name: str
    dataset_version: str
    split: str
    configuration: dict[str, Any]
    metrics: dict[str, Any]
    git_commit: str | None
    created_at: Any


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experiment: Literal["retrieval"]
    split: Literal["dev", "test"] = "test"


def _summary(run: EvaluationRun, full: bool) -> EvaluationSummary:
    metrics = run.metrics if full else {k: v for k, v in run.metrics.items() if k not in HEAVY_KEYS}
    return EvaluationSummary(
        id=run.id,
        experiment_name=run.experiment_name,
        dataset_version=run.dataset_version,
        split=run.split,
        configuration=run.configuration,
        metrics=metrics,
        git_commit=run.git_commit,
        created_at=run.created_at,
    )


def _run_retrieval(split: str) -> None:
    from app.cli import main as cli

    cli(["eval-retrieval", "--split", split])


def runner_dependency() -> Callable[[str], None]:
    return _run_retrieval


@router.get("", response_model=list[EvaluationSummary])
def list_runs(
    _: CurrentAdmin,
    session: DbSession,
    experiment: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[EvaluationSummary]:
    stmt = select(EvaluationRun).order_by(EvaluationRun.created_at.desc()).limit(limit)
    if experiment:
        stmt = stmt.where(EvaluationRun.experiment_name == experiment)
    return [_summary(r, full=False) for r in session.scalars(stmt)]


@router.get("/{run_id}", response_model=EvaluationSummary)
def get_run(run_id: uuid.UUID, _: CurrentAdmin, session: DbSession) -> EvaluationSummary:
    run = session.get(EvaluationRun, run_id)
    if run is None:
        raise NotFoundError("Evaluation run not found")
    return _summary(run, full=True)


@router.post("/run", status_code=status.HTTP_202_ACCEPTED)
def start_run(
    body: RunRequest,
    _: CurrentAdmin,
    background: BackgroundTasks,
    runner: Annotated[Callable[[str], None], Depends(runner_dependency)],
) -> dict[str, str]:
    background.add_task(runner, body.split)
    return {"status": "started", "experiment": body.experiment, "split": body.split}
