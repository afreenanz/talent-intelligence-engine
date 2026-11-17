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
    r = client.post(
        "/api/v1/jobs/search",
        json={"query": "python backend", "top_k": 5, "ranking": "none"},
        headers=h,
    )
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


def test_default_search_is_ranked_with_explanations(client: TestClient) -> None:
    h = auth_header(register_and_login(client))
    body = client.post("/api/v1/jobs/search", json={"query": "python backend"}, headers=h).json()
    assert body["ranking"] == "features" and body["weights_version"] == "weighted_v1"
    hit = body["results"][0]
    assert hit["score"] is not None and hit["explanation"]
    assert set(hit["features"]) >= {"required_skill_coverage", "semantic_similarity"}


def test_recommendations_use_profile_and_cross_encoder_option(client: TestClient) -> None:
    from app.domains.ranking.deps import reranker_provider_dependency
    from tests.fakes import KeywordReranker

    reranker = KeywordReranker()
    app.dependency_overrides[reranker_provider_dependency] = lambda: lambda: reranker
    try:
        h = auth_header(register_and_login(client))
        client.put(
            "/api/v1/candidates/me",
            json={"skills": [{"name": "Python"}], "profile_summary": "Backend developer"},
            headers=h,
        )
        r = client.get(
            "/api/v1/recommendations", params={"ranking": "features+cross_encoder"}, headers=h
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["used_profile"] is True and body["results"]
        assert body["results"][0]["cross_encoder_score"] is not None and reranker.calls
    finally:
        app.dependency_overrides.pop(reranker_provider_dependency, None)


def test_recommendations_with_empty_profile_is_clear_error(client: TestClient) -> None:
    h = auth_header(register_and_login(client))
    r = client.get("/api/v1/recommendations", headers=h)
    assert r.status_code == 400 and "profile is empty" in r.json()["error"]["message"]
