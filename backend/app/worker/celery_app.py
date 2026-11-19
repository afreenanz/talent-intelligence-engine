"""Celery application: background work that shouldn't run inside a web request.

Broker: Redis (already part of the stack). No result backend: callers never wait on a task;
outcomes are written to Postgres (resume status, evaluation_runs), which is the source of truth.

Reliability settings (see docs/engineering-decisions.md, ADR-014):
- acks_late + prefetch 1: a task is acknowledged only after it finishes, so a worker crash puts
  it back on the queue instead of losing it. Tasks must therefore be idempotent (they are:
  process_resume claims the row atomically; expiry and requeue are set-based updates).
- time limits: an LLM call that hangs can't hold a worker forever.
"""

from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery("talent_engine", broker=settings.redis_url, include=["app.worker.tasks"])
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=240,
    task_time_limit=300,
    broker_connection_retry_on_startup=True,
    timezone="UTC",
    beat_schedule={
        "expire-due-jobs": {"task": "app.worker.tasks.expire_jobs", "schedule": crontab(minute=5)},
        # Once a day, early morning UTC: well inside Adzuna's free limits (12 requests/run).
        "refresh-job-feed": {
            "task": "app.worker.tasks.refresh_job_feed",
            "schedule": crontab(hour=1, minute=30),
        },
        "requeue-stale-resumes": {
            "task": "app.worker.tasks.requeue_stale_resumes",
            "schedule": 300.0,
        },
    },
)
