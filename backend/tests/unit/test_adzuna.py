"""Adzuna mapping and client, against the documented response shape (no network)."""

import json
from pathlib import Path

import httpx
import pytest

from app.domains.ingestion.schemas import JobRecordIn
from app.integrations.job_feeds.adzuna import AdzunaClient, map_result

FIXTURE = json.loads((Path(__file__).parents[1] / "fixtures" / "adzuna_search_in.json").read_text())
R = FIXTURE["results"]


def test_maps_a_full_result_into_a_valid_job_record() -> None:
    rec = map_result(R[0], "in")
    assert rec is not None
    assert rec["title"] == "Senior Backend Engineer & Platform"  # tags stripped, entities decoded
    assert rec["company"] == "Acme Fintech Pvt Ltd"
    assert rec["location"] == "Bengaluru, Karnataka"
    assert rec["location_type"] == "hybrid"
    assert rec["employment_type"] == "full_time"
    assert (rec["salary_min"], rec["salary_max"], rec["salary_currency"]) == (
        1800000,
        2600000,
        "INR",
    )
    assert rec["apply_url"].startswith("https://www.adzuna.in/")
    assert rec["expires_at"].startswith("2026-12-15")  # 30 days after posting
    JobRecordIn.model_validate(rec)  # passes the same contract as a file import


def test_never_presents_a_predicted_salary_as_stated() -> None:
    rec = map_result(R[1], "in")
    assert rec is not None
    assert "salary_min" not in rec and "salary_currency" not in rec
    assert rec["location_type"] == "remote"  # "work from home"
    assert rec["employment_type"] == "contract"


def test_skips_results_without_a_company_and_unknown_currencies() -> None:
    assert map_result(R[2], "in") is None
    rec = map_result(R[0], "zz")  # a country we have no currency for
    assert rec is not None and "salary_min" not in rec


def _client(handler: httpx.MockTransport) -> AdzunaClient:
    return AdzunaClient("id", "key", "in", http=httpx.Client(transport=handler), pause_seconds=0)


def test_fetch_deduplicates_and_reports_what_it_skipped() -> None:
    calls: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        return httpx.Response(200, json=FIXTURE)

    records, stats = _client(httpx.MockTransport(handler)).fetch(["backend developer"], pages=3)
    assert [r["external_id"] for r in records] == [
        "4954512345",
        "4954599999",
    ]  # duplicate id dropped
    assert stats.skipped == 1 and stats.requests == 1  # 4 < 50 results: no second page requested
    q = calls[0].url.params
    assert calls[0].url.path == "/v1/api/jobs/in/search/1"
    assert q["what"] == "backend developer" and q["app_id"] == "id" and q["max_days_old"] == "30"


@pytest.mark.parametrize(("status", "reason"), [(401, "rejected the API key"), (429, "rate limit")])
def test_stops_early_but_keeps_what_it_already_has(status: int, reason: str) -> None:
    responses = iter([httpx.Response(200, json=FIXTURE), httpx.Response(status)])
    records, stats = _client(httpx.MockTransport(lambda _r: next(responses))).fetch(["a", "b"])
    assert len(records) == 2  # from the first query
    assert stats.stopped_early is not None and reason in stats.stopped_early
