from fastapi.testclient import TestClient


def test_live(client: TestClient) -> None:
    r = client.get("/health/live")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_ready_checks_database_and_redis(client: TestClient) -> None:
    r = client.get("/health/ready")
    assert r.status_code == 200, r.text
    assert r.json()["checks"] == {"database": "ok", "redis": "ok"}


def test_request_id_is_generated_or_propagated(client: TestClient) -> None:
    assert len(client.get("/health/live").headers["x-request-id"]) == 32
    r = client.get("/health/live", headers={"X-Request-ID": "trace-abc-123"})
    assert r.headers["x-request-id"] == "trace-abc-123"


def test_malformed_request_id_is_replaced(client: TestClient) -> None:
    r = client.get("/health/live", headers={"X-Request-ID": "bad id\nwith newline"})
    assert r.headers["x-request-id"] != "bad id\nwith newline"


def test_unknown_route_uses_error_envelope(client: TestClient) -> None:
    r = client.get("/api/v1/does-not-exist")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"
