from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domains.ingestion import service as ingestion

pytestmark = pytest.mark.usefixtures("taxonomy")


def test_public_stats_count_only_active_jobs(client: TestClient, db_session: Session) -> None:
    now = datetime.now(UTC)
    ingestion.ingest(
        db_session,
        [
            {
                "external_id": "1",
                "title": "Backend Engineer",
                "company": "Acme",
                "description": "x" * 40,
            },
            {
                "external_id": "2",
                "title": "Data Engineer",
                "company": "Acme",
                "description": "y" * 40,
            },
            {
                "external_id": "3",
                "title": "C",
                "company": "Bluefin",
                "description": "z" * 40,
                "posted_at": "2020-01-01T00:00:00",
                "expires_at": "2020-02-01T00:00:00",
            },
        ],
        source="s",
        now=now,
    )
    body = client.get("/api/v1/stats").json()  # no auth needed
    assert body["active_jobs"] == 2 and body["companies_hiring"] == 1
    assert body["skills_tracked"] > 100  # curated taxonomy
