from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.auth.models import RefreshToken, User
from tests.conftest import auth_header, register_and_login

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"
LOGOUT = "/api/v1/auth/logout"
ME = "/api/v1/candidates/me"


def test_register_normalises_email_and_hides_password(client: TestClient) -> None:
    r = client.post(REGISTER, json={"email": "Bob@Example.COM", "password": "long-enough-pw"})
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "bob@example.com"
    assert "password" not in body and "password_hash" not in body


def test_register_stores_argon2_hash_not_plaintext(client: TestClient, db_session: Session) -> None:
    client.post(REGISTER, json={"email": "h@example.com", "password": "long-enough-pw"})
    user = db_session.scalar(select(User).where(User.email == "h@example.com"))
    assert user is not None
    assert user.password_hash.startswith("$argon2id$")
    assert "long-enough-pw" not in user.password_hash


def test_duplicate_email_is_conflict_case_insensitive(client: TestClient) -> None:
    client.post(REGISTER, json={"email": "dup@example.com", "password": "long-enough-pw"})
    r = client.post(REGISTER, json={"email": "DUP@example.com", "password": "long-enough-pw"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "conflict"


def test_short_password_rejected_without_echoing_input(client: TestClient) -> None:
    r = client.post(REGISTER, json={"email": "s@example.com", "password": "short"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"
    assert "short" not in r.text.replace("too_short", "").replace("should have", "")


def test_register_rejects_extra_fields(client: TestClient) -> None:
    r = client.post(
        REGISTER, json={"email": "x@example.com", "password": "long-enough-pw", "is_admin": True}
    )
    assert r.status_code == 422


def test_login_success_returns_token_pair(client: TestClient) -> None:
    tokens = register_and_login(client)
    assert tokens["token_type"] == "bearer"
    assert tokens["expires_in"] == 15 * 60
    assert tokens["access_token"] and tokens["refresh_token"]


def test_wrong_password_and_unknown_email_are_indistinguishable(client: TestClient) -> None:
    register_and_login(client, "known@example.com")
    wrong_pw = client.post(LOGIN, json={"email": "known@example.com", "password": "nope-nope"})
    unknown = client.post(LOGIN, json={"email": "ghost@example.com", "password": "nope-nope"})
    assert wrong_pw.status_code == unknown.status_code == 401
    assert wrong_pw.json()["error"]["message"] == unknown.json()["error"]["message"]


def test_inactive_user_cannot_login_or_use_token(client: TestClient, db_session: Session) -> None:
    tokens = register_and_login(client, "inactive@example.com")
    user = db_session.scalar(select(User).where(User.email == "inactive@example.com"))
    assert user is not None
    user.is_active = False
    db_session.flush()
    assert client.get(ME, headers=auth_header(tokens)).status_code == 401
    r = client.post(
        LOGIN, json={"email": "inactive@example.com", "password": "correct-horse-battery"}
    )
    assert r.status_code == 401


def test_refresh_rotates_token(client: TestClient) -> None:
    tokens = register_and_login(client)
    r = client.post(REFRESH, json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 200
    new = r.json()
    assert new["refresh_token"] != tokens["refresh_token"]
    assert client.get(ME, headers=auth_header(new)).status_code == 200


def test_refresh_token_reuse_revokes_all_sessions(client: TestClient, db_session: Session) -> None:
    tokens = register_and_login(client)
    rotated = client.post(REFRESH, json={"refresh_token": tokens["refresh_token"]}).json()

    # Old token presented again -> treated as theft: rejected AND the rotated token is revoked.
    reuse = client.post(REFRESH, json={"refresh_token": tokens["refresh_token"]})
    assert reuse.status_code == 401
    after = client.post(REFRESH, json={"refresh_token": rotated["refresh_token"]})
    assert after.status_code == 401
    assert all(t.revoked_at is not None for t in db_session.scalars(select(RefreshToken)))


def test_logout_revokes_refresh_token_and_is_idempotent(client: TestClient) -> None:
    tokens = register_and_login(client)
    assert client.post(LOGOUT, json={"refresh_token": tokens["refresh_token"]}).status_code == 204
    assert client.post(LOGOUT, json={"refresh_token": tokens["refresh_token"]}).status_code == 204
    r = client.post(REFRESH, json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 401


def test_refresh_token_cannot_be_used_as_access_token(client: TestClient) -> None:
    tokens = register_and_login(client)
    r = client.get(ME, headers={"Authorization": f"Bearer {tokens['refresh_token']}"})
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


def test_me_returns_account_with_admin_flag(client: TestClient) -> None:
    tokens = register_and_login(client, "me@example.com")
    body = client.get("/api/v1/auth/me", headers=auth_header(tokens)).json()
    assert body["email"] == "me@example.com" and body["is_admin"] is False
    assert client.get("/api/v1/auth/me").status_code == 401


def test_signup_can_be_closed_for_a_public_demo(client: TestClient) -> None:
    from app.core.config import get_settings
    from app.main import app

    closed = get_settings().model_copy(update={"signup_enabled": False})
    app.dependency_overrides[get_settings] = lambda: closed
    r = client.post(
        "/api/v1/auth/register", json={"email": "new@example.com", "password": "long-enough-pw"}
    )
    assert r.status_code == 403
    assert "demo account" in r.json()["error"]["message"]
