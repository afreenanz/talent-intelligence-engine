"""Saved jobs, applications, feedback, search logging and explicit preferences."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.enums import InteractionType
from app.domains.ingestion import service as ingestion
from app.domains.interactions.models import JobInteraction
from app.domains.jobs.models import Job
from app.domains.search.deps import embedder_dependency
from app.domains.search.indexing import embed_jobs
from app.main import app
from tests.conftest import auth_header, register_and_login
from tests.fakes import HashingEmbedder

pytestmark = pytest.mark.usefixtures("taxonomy")
NOW = datetime.now(UTC)
DESC = " role building payment services, owned end to end with a small product team."


@pytest.fixture
def jobs(db_session: Session) -> Iterator[dict[str, str]]:
    ingestion.ingest(
        db_session,
        [
            {
                "external_id": "a",
                "title": "Backend Engineer",
                "company": "Acme",
                "description": "Backend" + DESC,
            },
            {
                "external_id": "b",
                "title": "Data Engineer",
                "company": "Bluefin",
                "description": "Data" + DESC,
            },
            {
                "external_id": "old",
                "title": "Old Role",
                "company": "Coral",
                "description": "Old" + DESC,
                "posted_at": (NOW - timedelta(days=60)).isoformat(),
                "expires_at": (NOW - timedelta(days=1)).isoformat(),
            },
        ],
        source="act",
        now=NOW,
    )
    emb = HashingEmbedder()
    embed_jobs(db_session, emb)
    app.dependency_overrides[embedder_dependency] = lambda: emb
    ids = {j.external_id: str(j.id) for j in db_session.scalars(select(Job))}
    yield ids
    app.dependency_overrides.pop(embedder_dependency, None)


def events(db: Session, kind: InteractionType) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(JobInteraction)
            .where(JobInteraction.interaction_type == kind)
        )
        or 0
    )


# ---------------------------------------------------------------- saved jobs


def test_save_is_idempotent_and_logs_only_real_changes(
    client: TestClient, db_session: Session, jobs: dict[str, str]
) -> None:
    h = auth_header(register_and_login(client))
    first = client.post("/api/v1/saved-jobs", json={"job_id": jobs["a"]}, headers=h)
    again = client.post("/api/v1/saved-jobs", json={"job_id": jobs["a"]}, headers=h)
    assert (first.status_code, first.json()["created"]) == (201, True)
    assert (again.status_code, again.json()["created"]) == (200, False)
    assert events(db_session, InteractionType.SAVE) == 1

    page = client.get("/api/v1/saved-jobs", headers=h).json()
    assert [i["job"]["title"] for i in page["items"]] == ["Backend Engineer"]

    assert client.delete(f"/api/v1/saved-jobs/{jobs['a']}", headers=h).status_code == 204
    assert client.delete(f"/api/v1/saved-jobs/{jobs['a']}", headers=h).status_code == 204
    assert events(db_session, InteractionType.UNSAVE) == 1
    assert client.get("/api/v1/saved-jobs", headers=h).json()["items"] == []


def test_saving_unavailable_or_unknown_jobs(client: TestClient, jobs: dict[str, str]) -> None:
    h = auth_header(register_and_login(client))
    r = client.post("/api/v1/saved-jobs", json={"job_id": jobs["old"]}, headers=h)
    assert r.status_code == 409 and r.json()["error"]["code"] == "job_unavailable"
    r = client.post(
        "/api/v1/saved-jobs", json={"job_id": "00000000-0000-0000-0000-000000000000"}, headers=h
    )
    assert r.status_code == 404


def test_saved_jobs_paginate(client: TestClient, jobs: dict[str, str]) -> None:
    h = auth_header(register_and_login(client))
    for k in ("a", "b"):
        client.post("/api/v1/saved-jobs", json={"job_id": jobs[k]}, headers=h)
    p1 = client.get("/api/v1/saved-jobs", params={"limit": 1}, headers=h).json()
    p2 = client.get(
        "/api/v1/saved-jobs", params={"limit": 1, "cursor": p1["next_cursor"]}, headers=h
    ).json()
    assert len(p1["items"]) == len(p2["items"]) == 1 and p2["next_cursor"] is None
    assert p1["items"][0]["job"]["id"] != p2["items"][0]["job"]["id"]


# ---------------------------------------------------------------- applications


def test_application_lifecycle(
    client: TestClient, db_session: Session, jobs: dict[str, str]
) -> None:
    h = auth_header(register_and_login(client))
    r = client.post(
        "/api/v1/applications", json={"job_id": jobs["a"], "notes": "referral"}, headers=h
    )
    assert r.status_code == 201 and r.json()["application_status"] == "applied"
    app_id = r.json()["id"]
    assert events(db_session, InteractionType.APPLY) == 1
    assert (
        client.post("/api/v1/applications", json={"job_id": jobs["a"]}, headers=h).status_code
        == 409
    )

    ok = client.patch(
        f"/api/v1/applications/{app_id}", json={"application_status": "screening"}, headers=h
    )
    assert ok.status_code == 200 and ok.json()["application_status"] == "screening"
    bad = client.patch(
        f"/api/v1/applications/{app_id}", json={"application_status": "applied"}, headers=h
    )
    assert bad.status_code == 409
    assert set(bad.json()["error"]["details"]["allowed"]) == {
        "interviewing",
        "rejected",
        "withdrawn",
    }
    client.patch(
        f"/api/v1/applications/{app_id}", json={"application_status": "withdrawn"}, headers=h
    )
    final = client.patch(
        f"/api/v1/applications/{app_id}", json={"application_status": "screening"}, headers=h
    )
    assert (
        final.status_code == 409 and final.json()["error"]["details"]["allowed"] == []
    )  # terminal


def test_cannot_apply_to_expired_job(client: TestClient, jobs: dict[str, str]) -> None:
    h = auth_header(register_and_login(client))
    assert (
        client.post("/api/v1/applications", json={"job_id": jobs["old"]}, headers=h).status_code
        == 409
    )


def test_activity_is_private(client: TestClient, jobs: dict[str, str]) -> None:
    alice = auth_header(register_and_login(client, "alice@example.com"))
    bob = auth_header(register_and_login(client, "bob@example.com"))
    client.post("/api/v1/saved-jobs", json={"job_id": jobs["a"]}, headers=alice)
    app_id = client.post("/api/v1/applications", json={"job_id": jobs["a"]}, headers=alice).json()[
        "id"
    ]
    assert client.get("/api/v1/saved-jobs", headers=bob).json()["items"] == []
    assert client.get("/api/v1/applications", headers=bob).json() == []
    r = client.patch(
        f"/api/v1/applications/{app_id}", json={"application_status": "withdrawn"}, headers=bob
    )
    assert r.status_code == 404


# ---------------------------------------------------------------- search logging and feedback


def test_search_logs_impressions_and_feedback_attribution(
    client: TestClient, db_session: Session, jobs: dict[str, str]
) -> None:
    h = auth_header(register_and_login(client))
    body = client.post("/api/v1/jobs/search", json={"query": "backend engineer"}, headers=h).json()
    log_id = body["search_log_id"]
    shown = [r["job_id"] for r in body["results"]]
    positions = list(
        db_session.scalars(
            select(JobInteraction.position)
            .where(JobInteraction.interaction_type == InteractionType.IMPRESSION)
            .order_by(JobInteraction.position)
        )
    )
    assert positions == list(range(1, len(shown) + 1))

    r = client.post(
        "/api/v1/recommendations/feedback",
        headers=h,
        json={
            "job_id": shown[0],
            "interaction_type": "click",
            "search_log_id": log_id,
            "position": 1,
        },
    )
    assert r.status_code == 201 and events(db_session, InteractionType.CLICK) == 1
    recent = client.get("/api/v1/candidates/me/searches", headers=h).json()
    assert recent[0]["query"] == "backend engineer"


def test_feedback_rejects_foreign_search_and_wrong_type(
    client: TestClient, jobs: dict[str, str]
) -> None:
    alice = auth_header(register_and_login(client, "alice@example.com"))
    bob = auth_header(register_and_login(client, "bob@example.com"))
    log_id = client.post("/api/v1/jobs/search", json={"query": "data"}, headers=alice).json()[
        "search_log_id"
    ]
    r = client.post(
        "/api/v1/recommendations/feedback",
        headers=bob,
        json={"job_id": jobs["b"], "interaction_type": "dismiss", "search_log_id": log_id},
    )
    assert r.status_code == 404
    r = client.post(
        "/api/v1/recommendations/feedback",
        headers=bob,
        json={"job_id": jobs["b"], "interaction_type": "save"},
    )
    assert r.status_code == 400


# ---------------------------------------------------------------- preferences


def _put(client: TestClient, h: dict[str, str], key: str, value: dict[str, Any]) -> Any:
    return client.put(f"/api/v1/candidates/me/preferences/{key}", json={"value": value}, headers=h)


def test_preference_upsert_reports_previous_value(client: TestClient) -> None:
    h = auth_header(register_and_login(client))
    first = _put(client, h, "role_categories", {"prefer": ["backend"], "avoid": ["frontend"]})
    assert (
        first.status_code == 200
        and first.json()["created"] is True
        and first.json()["previous"] is None
    )
    second = _put(client, h, "role_categories", {"prefer": ["backend", "data"]})
    assert second.json()["previous"] == {"prefer": ["backend"], "avoid": ["frontend"]}
    listed = client.get("/api/v1/candidates/me/preferences", headers=h).json()
    assert len(listed) == 1 and listed[0]["value"]["prefer"] == ["backend", "data"]
    assert listed[0]["source"] == "settings" and listed[0]["confidence"] == 1.0


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("role_categories", {"prefer": ["backend"], "avoid": ["backend"]}),
        ("role_categories", {"prefer": ["astronaut"]}),
        ("min_salary", {"amount": -5}),
        ("location_type", {"value": "moon"}),
        ("locations", {"cities": [], "extra": 1}),
    ],
)
def test_invalid_preference_values_are_422_not_500(
    client: TestClient, key: str, value: dict[str, Any]
) -> None:
    h = auth_header(register_and_login(client))
    r = _put(client, h, key, value)
    assert r.status_code == 422 and r.json()["error"]["details"]


def test_unknown_key_and_delete(client: TestClient) -> None:
    h = auth_header(register_and_login(client))
    assert _put(client, h, "favourite_colour", {"value": "blue"}).status_code == 422
    _put(client, h, "location_type", {"value": "remote"})
    assert (
        client.delete("/api/v1/candidates/me/preferences/location_type", headers=h).status_code
        == 204
    )
    assert (
        client.delete("/api/v1/candidates/me/preferences/location_type", headers=h).status_code
        == 404
    )


def test_preferences_are_private(client: TestClient) -> None:
    alice = auth_header(register_and_login(client, "alice@example.com"))
    bob = auth_header(register_and_login(client, "bob@example.com"))
    _put(client, alice, "location_type", {"value": "remote"})
    assert client.get("/api/v1/candidates/me/preferences", headers=bob).json() == []
