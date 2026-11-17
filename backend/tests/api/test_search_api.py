from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domains.ingestion import service as ingestion
from app.domains.search.deps import embedder_dependency
from app.domains.search.indexing import embed_jobs
from app.main import app
from tests.conftest import auth_header, register_and_login
from tests.fakes import HashingEmbedder

pytestmark = pytest.mark.usefixtures("taxonomy")


@pytest.fixture(autouse=True)
def fake_embedder(db_session: Session) -> Iterator[HashingEmbedder]:
    emb = HashingEmbedder()
    ingestion.ingest(
        db_session,
        [
            {
                "external_id": "1",
                "title": "Backend Engineer",
                "company": "Acme",
                "description": "Python and PostgreSQL services for payments, owned end to end.",
                "location": "Pune",
            }
        ],
        source="api",
        now=datetime.now(UTC),
    )
    embed_jobs(db_session, emb)
    app.dependency_overrides[embedder_dependency] = lambda: emb
    yield emb
    app.dependency_overrides.pop(embedder_dependency, None)


def test_search_returns_ranks_scores_and_timings(client: TestClient) -> None:
    h = auth_header(register_and_login(client))
    r = client.post("/api/v1/jobs/search", json={"query": "python backend", "top_k": 5}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    hit = body["results"][0]
    assert hit["title"] == "Backend Engineer"
    assert hit["lexical_rank"] == 1 and hit["semantic_rank"] == 1 and hit["fused_score"] > 0
    assert {"lexical", "dense"} <= set(body["timings_ms"])


def test_search_validation_and_auth(client: TestClient) -> None:
    assert client.post("/api/v1/jobs/search", json={"query": "x"}).status_code == 401
    h = auth_header(register_and_login(client))
    assert (
        client.post("/api/v1/jobs/search", json={"query": "x", "top_k": 0}, headers=h).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/jobs/search", json={"query": "x", "mode": "magic"}, headers=h
        ).status_code
        == 422
    )
    empty = client.post("/api/v1/jobs/search", json={}, headers=h)
    assert empty.status_code == 400 and empty.json()["error"]["code"] == "empty_search"


def test_profile_mode_with_empty_profile_is_a_clear_error(client: TestClient) -> None:
    h = auth_header(register_and_login(client))
    r = client.post("/api/v1/jobs/search", json={"use_profile": True}, headers=h)
    assert r.status_code == 400 and "profile is empty" in r.json()["error"]["message"]
