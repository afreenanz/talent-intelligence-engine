from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.rate_limit import LOGIN, get_counter_store
from app.main import app
from tests.unit.test_rate_limit import FakeStore


@pytest.fixture
def limited(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    # A fixed clock: with real time, a window boundary falling mid-test would reset the count.
    monkeypatch.setattr("app.core.rate_limit.time.time", lambda: 1_000_000.0)
    settings = get_settings().model_copy(update={"rate_limits_enabled": True})
    store = FakeStore()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_counter_store] = lambda: store
    yield client


def test_login_is_limited_per_address_with_retry_after(limited: TestClient) -> None:
    body = {"email": "nobody@example.com", "password": "wrong-password-1"}
    for _ in range(LOGIN.limit):
        assert limited.post("/api/v1/auth/login", json=body).status_code == 401
    r = limited.post("/api/v1/auth/login", json=body)
    assert r.status_code == 429
    assert 1 <= int(r.headers["retry-after"]) <= LOGIN.window_seconds
    err = r.json()["error"]
    assert err["code"] == "rate_limited" and err["details"]["retry_after_seconds"] >= 1
