from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domains.ingestion import service
from tests.conftest import auth_header, register_and_login

NOW = datetime.now(UTC)
DESC = "A sufficiently long description for a synthetic test job about building APIs in Python."


def _seed(db: Session, n: int) -> None:
    records = [
        {
            "external_id": f"api-{i}",
            "title": f"Engineer {i}",
            "company": "Acme" if i % 2 else "Bluefin",
            "description": DESC,
            "location": "Pune" if i % 3 else "Remote (India)",
            "required_skills": ["Python"],
            "posted_at": (NOW - timedelta(hours=i)).isoformat(),
        }
        for i in range(n)
    ]
    service.ingest(db, records, source="api_test", now=NOW)


def test_jobs_require_auth(client: TestClient) -> None:
    assert client.get("/api/v1/jobs").status_code == 401


def test_keyset_pagination_walks_all_jobs_without_overlap(
    client: TestClient, db_session: Session
) -> None:
    _seed(db_session, 7)
    h = auth_header(register_and_login(client))
    seen: list[str] = []
    cursor = None
    while True:
        params = {"limit": 3, **({"cursor": cursor} if cursor else {})}
        page = client.get("/api/v1/jobs", params=params, headers=h).json()
        seen += [j["title"] for j in page["items"]]
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert seen == [f"Engineer {i}" for i in range(7)]  # newest first, each exactly once


def test_filters(client: TestClient, db_session: Session) -> None:
    _seed(db_session, 6)
    h = auth_header(register_and_login(client))
    remote = client.get("/api/v1/jobs", params={"location_type": "remote"}, headers=h).json()
    assert {j["title"] for j in remote["items"]} == {"Engineer 0", "Engineer 3"}
    pune = client.get("/api/v1/jobs", params={"city": "pune", "company": "acme"}, headers=h)
    assert {j["title"] for j in pune.json()["items"]} == {"Engineer 1", "Engineer 5"}


def test_like_wildcards_in_company_filter_are_literal(
    client: TestClient, db_session: Session
) -> None:
    _seed(db_session, 2)
    h = auth_header(register_and_login(client))
    r = client.get("/api/v1/jobs", params={"company": "%"}, headers=h).json()
    assert r["items"] == []


def test_invalid_cursor_is_a_400(client: TestClient) -> None:
    h = auth_header(register_and_login(client))
    r = client.get("/api/v1/jobs", params={"cursor": "not-a-cursor"}, headers=h)
    assert r.status_code == 400


def test_job_detail_includes_skills_and_404(client: TestClient, db_session: Session) -> None:
    _seed(db_session, 1)
    h = auth_header(register_and_login(client))
    job_id = client.get("/api/v1/jobs", headers=h).json()["items"][0]["id"]
    detail = client.get(f"/api/v1/jobs/{job_id}", headers=h).json()
    assert detail["description"] == DESC
    assert {(s["name"], s["importance"]) for s in detail["skills"]} >= {("Python", "required")}
    missing = client.get("/api/v1/jobs/00000000-0000-0000-0000-000000000000", headers=h)
    assert missing.status_code == 404
