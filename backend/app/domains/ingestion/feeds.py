"""Refresh jobs from a live feed: fetch -> the normal ingestion pipeline -> embed what changed.

The feed goes through exactly the same validation, normalisation, deduplication and expiry as a
file import; the only differences are the source name and that records carry an `apply_url`.
"""

from dataclasses import dataclass

import structlog
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.enums import IngestionMode
from app.domains.ingestion import service as ingestion
from app.domains.ingestion.models import IngestionRun
from app.integrations.job_feeds.adzuna import AdzunaClient, FetchStats, source_name

log = structlog.get_logger()


class FeedNotConfiguredError(Exception):
    pass


@dataclass
class FeedRefresh:
    stats: FetchStats
    run: IngestionRun | None


def adzuna_client(settings: Settings) -> AdzunaClient:
    if not settings.adzuna_app_id or not settings.adzuna_app_key:
        raise FeedNotConfiguredError("Set ADZUNA_APP_ID and ADZUNA_APP_KEY to use the Adzuna feed")
    return AdzunaClient(
        settings.adzuna_app_id, settings.adzuna_app_key.get_secret_value(), settings.adzuna_country
    )


def refresh_adzuna(
    session: Session,
    settings: Settings,
    client: AdzunaClient | None = None,
    queries: list[str] | None = None,
) -> FeedRefresh:
    client = client or adzuna_client(settings)
    records, stats = client.fetch(
        queries or settings.job_feed_queries,
        pages=settings.job_feed_pages,
        max_days_old=settings.job_feed_max_days_old,
    )
    if not records:
        log.warning(
            "job_feed_empty", source=source_name(client.country), reason=stats.stopped_early
        )
        return FeedRefresh(stats, None)
    run = ingestion.ingest(
        session,
        records,
        source=source_name(client.country),
        mode=IngestionMode.INCREMENTAL,  # a search API never returns "everything": no snapshot
        file_name=f"adzuna api ({stats.requests} requests)",
    )
    log.info(
        "job_feed_ingested",
        source=run.source,
        requests=stats.requests,
        usable=stats.usable,
        inserted=run.inserted,
        updated=run.updated,
        duplicates=run.duplicates,
        failed=run.failed,
    )
    return FeedRefresh(stats, run)
