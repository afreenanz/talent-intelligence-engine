"""A feed refresh goes through the real ingestion pipeline, idempotently, and stays separable."""

import json
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domains.ingestion.feeds import refresh_adzuna
from app.domains.jobs.models import Job
from app.integrations.job_feeds.adzuna import AdzunaClient

FIXTURE = json.loads((Path(__file__).parents[1] / "fixtures" / "adzuna_search_in.json").read_text())


def _client() -> AdzunaClient:
    transport = httpx.MockTransport(lambda _r: httpx.Response(200, json=FIXTURE))
    return AdzunaClient("id", "key", "in", http=httpx.Client(transport=transport), pause_seconds=0)


def test_refresh_ingests_once_and_is_idempotent(db_session: Session, taxonomy: None) -> None:
    first = refresh_adzuna(db_session, get_settings(), _client(), ["backend developer"])
    assert first.run is not None and first.run.inserted == 2 and first.run.failed == 0
    job = db_session.scalar(
        select(Job).where(Job.source == "adzuna_in", Job.external_id == "4954512345")
    )
    assert job is not None
    assert job.apply_url and job.apply_url.startswith("https://www.adzuna.in/")
    assert job.city == "Bengaluru" and job.salary_currency == "INR"
    assert {s.skill.name for s in job.skills} >= {"Python", "FastAPI", "PostgreSQL", "Docker"}

    again = refresh_adzuna(db_session, get_settings(), _client(), ["backend developer"])
    assert again.run is not None and again.run.inserted == 0 and again.run.unchanged == 2
