from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.demo import DEMO_EMAIL, seed_demo


def test_demo_account_can_sign_in_and_is_ready_for_matches(
    client: TestClient, db_session: Session, taxonomy: None
) -> None:
    _, created = seed_demo(db_session, "first-password-1")
    assert created
    _, created = seed_demo(db_session, "second-password-2")  # idempotent: resets, doesn't duplicate
    assert not created

    assert (
        client.post(
            "/api/v1/auth/login", json={"email": DEMO_EMAIL, "password": "first-password-1"}
        ).status_code
        == 401
    )
    r = client.post(
        "/api/v1/auth/login", json={"email": DEMO_EMAIL, "password": "second-password-2"}
    )
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    me = client.get("/api/v1/candidates/me", headers=h).json()
    assert me["full_name"] == "Demo Candidate" and len(me["skills"]) == 7
    prefs = client.get("/api/v1/candidates/me/preferences", headers=h).json()
    assert prefs[0]["value"]["prefer"] == ["backend"]
