from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.auth.models import User
from app.domains.candidates.models import CandidateProfile
from app.domains.skills.models import Skill, SkillAlias
from tests.conftest import auth_header, register_and_login

ME = "/api/v1/candidates/me"


def _full_profile(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "full_name": "Alice Doe",
        "experience_years": 2.5,
        "education": [{"institution": "IIT Madras", "degree": "B.Tech", "end_year": 2024}],
        "projects": [{"name": "Search engine", "technologies": ["Python", "Postgres"]}],
        "location": "Bangalore",
        "preferred_salary_min": 1_500_000,
        "preferred_salary_max": 2_500_000,
        "preferred_job_type": "full_time",
        "preferred_location_type": "hybrid",
        "profile_summary": "Backend engineer.",
        "skills": [{"name": "Python", "proficiency": 4}, {"name": "FastAPI"}],
    }
    body.update(overrides)
    return body


def test_profile_requires_authentication(client: TestClient) -> None:
    r = client.get(ME)
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthenticated"


def test_registration_creates_empty_profile(client: TestClient) -> None:
    client.post(
        "/api/v1/auth/register",
        json={"email": "p@example.com", "password": "long-enough-pw", "full_name": "Pat"},
    )
    tokens = client.post(
        "/api/v1/auth/login", json={"email": "p@example.com", "password": "long-enough-pw"}
    ).json()
    body = client.get(ME, headers=auth_header(tokens)).json()
    assert body["full_name"] == "Pat"
    assert body["skills"] == [] and body["education"] == []
    assert body["salary_currency"] == "INR"


def test_update_and_read_back_profile(client: TestClient) -> None:
    h = auth_header(register_and_login(client))
    r = client.put(ME, json=_full_profile(), headers=h)
    assert r.status_code == 200, r.text
    body = client.get(ME, headers=h).json()
    assert body["experience_years"] == 2.5
    assert body["preferred_location_type"] == "hybrid"
    assert body["education"][0]["institution"] == "IIT Madras"
    assert {s["normalized_name"] for s in body["skills"]} == {"python", "fastapi"}


def test_skill_list_is_replaced_not_appended(client: TestClient) -> None:
    h = auth_header(register_and_login(client))
    client.put(ME, json=_full_profile(), headers=h)
    r = client.put(
        ME,
        json=_full_profile(skills=[{"name": "python", "proficiency": 5}, {"name": "Docker"}]),
        headers=h,
    )
    skills = {s["normalized_name"]: s for s in r.json()["skills"]}
    assert set(skills) == {"python", "docker"}  # fastapi removed, docker added
    assert skills["python"]["proficiency"] == 5  # existing skill updated in place


def test_skills_are_shared_vocabulary_across_candidates(
    client: TestClient, db_session: Session
) -> None:
    for email in ("a@example.com", "b@example.com"):
        h = auth_header(register_and_login(client, email))
        client.put(ME, json=_full_profile(skills=[{"name": "Kubernetes"}]), headers=h)
    count = db_session.scalar(
        select(func.count()).select_from(Skill).where(Skill.normalized_name == "kubernetes")
    )
    assert count == 1


def test_alias_resolves_to_canonical_skill(client: TestClient, db_session: Session) -> None:
    pg = Skill(name="PostgreSQL", normalized_name="postgresql", category="database")
    db_session.add(pg)
    db_session.flush()
    db_session.add(SkillAlias(alias="postgres", skill_id=pg.id))
    db_session.flush()

    h = auth_header(register_and_login(client))
    r = client.put(ME, json=_full_profile(skills=[{"name": "Postgres"}]), headers=h)
    assert r.json()["skills"][0]["name"] == "PostgreSQL"


def test_candidates_cannot_see_or_modify_each_other(client: TestClient) -> None:
    alice = auth_header(register_and_login(client, "alice@example.com"))
    bob = auth_header(register_and_login(client, "bob@example.com"))
    client.put(ME, json=_full_profile(full_name="Alice"), headers=alice)
    client.put(ME, json=_full_profile(full_name="Bob"), headers=bob)

    assert client.get(ME, headers=alice).json()["full_name"] == "Alice"
    assert client.get(ME, headers=bob).json()["full_name"] == "Bob"
    assert client.get(ME, headers=alice).json()["id"] != client.get(ME, headers=bob).json()["id"]


def test_client_cannot_target_another_profile_via_body(client: TestClient) -> None:
    h = auth_header(register_and_login(client))
    r = client.put(ME, json=_full_profile(id="00000000-0000-0000-0000-000000000001"), headers=h)
    assert r.status_code == 422


def test_invalid_salary_range_rejected(client: TestClient) -> None:
    h = auth_header(register_and_login(client))
    r = client.put(
        ME, json=_full_profile(preferred_salary_min=30, preferred_salary_max=10), headers=h
    )
    assert r.status_code == 422


def test_database_enforces_salary_constraint_independently(
    client: TestClient, db_session: Session
) -> None:
    """Defence in depth: even if API validation were bypassed, the DB rejects bad data."""
    register_and_login(client)
    user = db_session.scalar(select(User))
    assert user is not None
    profile = db_session.scalar(select(CandidateProfile).where(CandidateProfile.user_id == user.id))
    assert profile is not None
    profile.preferred_salary_min, profile.preferred_salary_max = 100, 10
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()
