"""Adzuna job search API (https://developer.adzuna.com).

Terms we follow (developer.adzuna.com/docs/terms_of_service):
- Allowed uses include "personal job search" and "personal and academic research".
- Every displayed advert is labelled "Adzuna", hyperlinked to the local Adzuna site
  (the frontend does this for every job from this source), and Adzuna is credited as the source.

Data notes:
- The API returns only a *snippet* of each description, so skill extraction sees less text than
  for a full posting. This is a known limitation, not hidden.
- Adzuna fills in an estimated salary when the ad has none (`salary_is_predicted` = 1). We drop
  those: an estimate must not be shown as if the employer stated it.
"""

import html
import re
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import structlog

log = structlog.get_logger()

API = "https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"
CURRENCY = {
    "in": "INR",
    "gb": "GBP",
    "us": "USD",
    "sg": "SGD",
    "au": "AUD",
    "ca": "CAD",
    "de": "EUR",
}
SITE = {"in": "https://www.adzuna.in", "gb": "https://www.adzuna.co.uk"}
# An ad's lifetime when the feed doesn't say: most listings close within a month.
DEFAULT_LIFETIME = timedelta(days=30)

_TAG = re.compile(r"<[^>]+>")
_REMOTE = re.compile(r"\b(remote|work from home|wfh)\b", re.IGNORECASE)
_HYBRID = re.compile(r"\bhybrid\b", re.IGNORECASE)


class FeedError(Exception):
    """The feed can't be used right now (bad key, rate limited, or down)."""


def source_name(country: str) -> str:
    return f"adzuna_{country}"


def _clean(text: object) -> str:
    """Adzuna wraps matched words in <strong>…</strong> and escapes entities."""
    return " ".join(html.unescape(_TAG.sub(" ", str(text or ""))).split())


def _predicted(value: object) -> bool:
    return str(value).strip() not in ("0", "False", "false", "")


def map_result(raw: dict[str, Any], country: str) -> dict[str, Any] | None:
    """One Adzuna result -> a JobRecordIn-shaped dict, or None when it can't be used."""
    title = _clean(raw.get("title"))
    company = _clean((raw.get("company") or {}).get("display_name"))
    description = _clean(raw.get("description"))
    if not raw.get("id") or len(title) < 2 or not company or len(description) < 20:
        return None

    text = f"{title} {description}"
    location_type = "remote" if _REMOTE.search(text) else "hybrid" if _HYBRID.search(text) else None

    employment = None
    if raw.get("contract_type") == "contract":
        employment = "contract"
    elif raw.get("contract_time") in ("full_time", "part_time"):
        employment = raw["contract_time"]

    record: dict[str, Any] = {
        "external_id": str(raw["id"]),
        "title": title,
        "company": company,
        "description": description,
        "location": _clean((raw.get("location") or {}).get("display_name")) or None,
        "location_type": location_type,
        "employment_type": employment,
        "apply_url": raw.get("redirect_url") or None,
    }
    if not _predicted(raw.get("salary_is_predicted")) and (
        raw.get("salary_min") or raw.get("salary_max")
    ):
        record |= {
            "salary_min": raw.get("salary_min"),
            "salary_max": raw.get("salary_max"),
            "salary_currency": CURRENCY.get(country),
            "salary_period": "annual",
        }
        if record["salary_currency"] is None:  # unknown country: don't guess a currency
            for k in ("salary_min", "salary_max", "salary_currency", "salary_period"):
                record.pop(k)
    created = raw.get("created")
    if created:
        posted = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
        posted = posted if posted.tzinfo else posted.replace(tzinfo=UTC)
        record["posted_at"] = posted.isoformat()
        record["expires_at"] = (posted + DEFAULT_LIFETIME).isoformat()
    return record


@dataclass
class FetchStats:
    requests: int = 0
    results: int = 0
    usable: int = 0
    skipped: int = 0
    stopped_early: str | None = None
    per_query: dict[str, int] = field(default_factory=dict)


class AdzunaClient:
    def __init__(
        self,
        app_id: str,
        app_key: str,
        country: str = "in",
        *,
        http: httpx.Client | None = None,
        pause_seconds: float = 1.0,
    ) -> None:
        self.app_id, self.app_key, self.country = app_id, app_key, country
        self.http = http or httpx.Client(timeout=20.0)
        self.pause = pause_seconds

    def search(
        self, what: str, page: int, results_per_page: int, max_days_old: int
    ) -> list[dict[str, Any]]:
        params: dict[str, str | int] = {
            "app_id": self.app_id,
            "app_key": self.app_key,
            "what": what,
            "results_per_page": results_per_page,
            "max_days_old": max_days_old,
            "content-type": "application/json",
        }
        url = API.format(country=self.country, page=page)
        for attempt in (1, 2):
            try:
                r = self.http.get(url, params=params)
            except httpx.HTTPError as exc:
                if attempt == 2:
                    raise FeedError(f"Adzuna unreachable: {exc.__class__.__name__}") from exc
                time.sleep(2 * self.pause)
                continue
            if r.status_code in (401, 403):
                raise FeedError(
                    "Adzuna rejected the API key (check ADZUNA_APP_ID / ADZUNA_APP_KEY)"
                )
            if r.status_code == 429:
                raise FeedError("Adzuna rate limit reached; try again later")
            if r.status_code >= 500 and attempt == 1:
                time.sleep(2 * self.pause)
                continue
            if r.status_code != 200:
                raise FeedError(f"Adzuna returned HTTP {r.status_code}")
            results = r.json().get("results") or []
            return [x for x in results if isinstance(x, dict)]
        return []  # pragma: no cover (loop always returns or raises)

    def fetch(
        self,
        queries: Iterable[str],
        pages: int = 1,
        results_per_page: int = 50,
        max_days_old: int = 30,
    ) -> tuple[list[dict[str, Any]], FetchStats]:
        """Run every query, map and de-duplicate by Adzuna id. Stops early (keeping what it has)
        if the feed refuses: a partial refresh is better than none."""
        stats, seen, records = FetchStats(), set[str](), list[dict[str, Any]]()
        for what in queries:
            for page in range(1, pages + 1):
                if stats.requests:
                    time.sleep(self.pause)  # stay well under the per-minute limit
                try:
                    results = self.search(what, page, results_per_page, max_days_old)
                except FeedError as exc:
                    stats.stopped_early = str(exc)
                    log.warning(
                        "job_feed_stopped", source=source_name(self.country), reason=str(exc)
                    )
                    return records, stats
                stats.requests += 1
                stats.results += len(results)
                for raw in results:
                    rec = map_result(raw, self.country)
                    if rec is None:
                        stats.skipped += 1
                    elif rec["external_id"] not in seen:
                        seen.add(rec["external_id"])
                        records.append(rec)
                        stats.per_query[what] = stats.per_query.get(what, 0) + 1
                if len(results) < results_per_page:
                    break  # no more pages for this query
        stats.usable = len(records)
        return records, stats
