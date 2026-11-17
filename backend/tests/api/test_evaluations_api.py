from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.auth.models import User
from app.domains.evaluation.models import EvaluationRun
from app.domains.evaluation.router import runner_dependency
from app.main import app
from tests.conftest import auth_header, register_and_login


@pytest.fixture
def started() -> Iterator[list[str]]:
    calls: list[str] = []
    app.dependency_overrides[runner_dependency] = lambda: calls.append
    yield calls
    app.dependency_overrides.pop(runner_dependency, None)


def _admin(client: TestClient, db: Session) -> dict[str, str]:
    h = auth_header(register_and_login(client, "admin@example.com"))
    user = db.scalar(select(User).where(User.email == "admin@example.com"))
    assert user is not None
    user.is_admin = True
    db.flush()
    return h


def test_evaluations_are_admin_only(client: TestClient) -> None:
    h = auth_header(register_and_login(client))
    assert client.get("/api/v1/evaluations", headers=h).status_code == 403
    assert (
        client.post(
            "/api/v1/evaluations/run", json={"experiment": "retrieval"}, headers=h
        ).status_code
        == 403
    )


def test_admin_lists_summaries_without_heavy_payloads(
    client: TestClient, db_session: Session
) -> None:
    db_session.add(
        EvaluationRun(
            experiment_name="retrieval_comparison",
            dataset_version="v1",
            split="test",
            configuration={"name": "x"},
            metrics={"mean": {"ndcg@10": 0.8}, "per_query": {"q1": {}}},
        )
    )
    db_session.flush()
    h = _admin(client, db_session)
    runs = client.get(
        "/api/v1/evaluations", params={"experiment": "retrieval_comparison"}, headers=h
    ).json()
    assert runs[0]["metrics"] == {"mean": {"ndcg@10": 0.8}}  # per_query stripped from the list
    detail = client.get(f"/api/v1/evaluations/{runs[0]['id']}", headers=h).json()
    assert "per_query" in detail["metrics"]
    assert (
        client.get(
            "/api/v1/evaluations/00000000-0000-0000-0000-000000000000", headers=h
        ).status_code
        == 404
    )


def test_only_the_free_experiment_can_be_started_over_http(
    client: TestClient, db_session: Session, started: list[str]
) -> None:
    h = _admin(client, db_session)
    ok = client.post(
        "/api/v1/evaluations/run", json={"experiment": "retrieval", "split": "dev"}, headers=h
    )
    assert ok.status_code == 202 and started == ["dev"]
    assert (
        client.post("/api/v1/evaluations/run", json={"experiment": "agent"}, headers=h).status_code
        == 422
    )
