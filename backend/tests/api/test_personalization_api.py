from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.ingestion import service as ingestion
from app.domains.jobs.models import Job
from app.domains.search.deps import embedder_dependency
from app.domains.search.indexing import embed_jobs
from app.main import app
from tests.conftest import auth_header, register_and_login
from tests.fakes import HashingEmbedder

pytestmark = pytest.mark.usefixtures("taxonomy")
TAIL = " engineer role building product features end to end with a small team in Pune."


@pytest.fixture
def jobs(db_session: Session) -> Iterator[dict[str, str]]:
    recs = [
        {
            "external_id": f"{fam}{i}",
            "title": f"{fam.title()} Engineer",
            "company": f"{fam} co {i}",
            "description": f"{fam}{TAIL}",
        }
        for fam in ("backend", "frontend")
        for i in range(4)
    ]
    ingestion.ingest(db_session, recs, source="pz", now=datetime.now(UTC))
    emb = HashingEmbedder()
    embed_jobs(db_session, emb)
    app.dependency_overrides[embedder_dependency] = lambda: emb
    yield {j.external_id: str(j.id) for j in db_session.scalars(select(Job))}
    app.dependency_overrides.pop(embedder_dependency, None)


def search(client: TestClient, h: dict[str, str], **kw: Any) -> list[dict[str, Any]]:
    body = {"query": "engineer role building product features", "top_k": 8, **kw}
    return client.post("/api/v1/jobs/search", json=body, headers=h).json()["results"]


def test_saves_create_a_derived_preference(client: TestClient, jobs: dict[str, str]) -> None:
    h = auth_header(register_and_login(client))
    for i in range(3):
        client.post("/api/v1/saved-jobs", json={"job_id": jobs[f"backend{i}"]}, headers=h)
    prefs = client.get("/api/v1/candidates/me/preferences", headers=h).json()
    derived = [p for p in prefs if p["memory_type"] == "derived_preference"]
    assert len(derived) == 1 and derived[0]["value"]["prefer"] == ["backend"]
    assert 0 < derived[0]["confidence"] < 1 and derived[0]["source"] == "derived"


def test_two_saves_are_not_enough_evidence(client: TestClient, jobs: dict[str, str]) -> None:
    h = auth_header(register_and_login(client))
    for i in range(2):
        client.post("/api/v1/saved-jobs", json={"job_id": jobs[f"backend{i}"]}, headers=h)
    assert client.get("/api/v1/candidates/me/preferences", headers=h).json() == []


def test_learned_preference_moves_backend_jobs_up_within_cap(
    client: TestClient, jobs: dict[str, str]
) -> None:
    h = auth_header(register_and_login(client))
    before = search(client, h)
    for i in range(3):
        client.post("/api/v1/saved-jobs", json={"job_id": jobs[f"backend{i}"]}, headers=h)
    after = search(client, h)
    top_after = [r["role_categories"] for r in after[:4]]
    assert all(cats == ["backend"] for cats in top_after)
    assert all(abs(r["personalization"]) <= 0.1 + 1e-9 for r in after)
    assert any(e.startswith("Based on your activity") for e in after[0]["explanation"])
    assert before != after


def test_explicit_preference_beats_learned_one(client: TestClient, jobs: dict[str, str]) -> None:
    h = auth_header(register_and_login(client))
    for i in range(3):
        client.post("/api/v1/saved-jobs", json={"job_id": jobs[f"backend{i}"]}, headers=h)
    client.put(
        "/api/v1/candidates/me/preferences/role_categories",
        json={"value": {"prefer": ["frontend"], "avoid": ["backend"]}},
        headers=h,
    )
    top = search(client, h)[0]
    assert top["role_categories"] == ["frontend"]
    assert "You prefer frontend roles" in top["explanation"]


def test_personalize_false_disables_adjustment(client: TestClient, jobs: dict[str, str]) -> None:
    h = auth_header(register_and_login(client))
    client.put(
        "/api/v1/candidates/me/preferences/role_categories",
        json={"value": {"prefer": ["frontend"]}},
        headers=h,
    )
    assert all(r["personalization"] == 0 for r in search(client, h, personalize=False))
