"""Background tasks. Each one opens its own DB session and is safe to run twice."""

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import or_, select, update

from app.db.enums import ResumeStatus
from app.db.session import get_sessionmaker
from app.worker.celery_app import celery_app

log = structlog.get_logger()

# A resume stuck this long was lost (broker down at upload, or a worker died mid-task).
STALE_AFTER = timedelta(minutes=10)


@celery_app.task(name="app.worker.tasks.process_resume")
def process_resume(resume_id: str) -> str:
    from app.domains.resumes import service
    from app.integrations.llm.factory import get_llm_provider

    with get_sessionmaker()() as session:
        status = service.process_resume(session, uuid.UUID(resume_id), get_llm_provider())
    log.info("task_process_resume_done", resume_id=resume_id, status=str(status))
    return str(status)


@celery_app.task(name="app.worker.tasks.run_retrieval_eval")
def run_retrieval_eval(split: str) -> None:
    from app.cli import main as cli

    cli(["eval-retrieval", "--split", split])


@celery_app.task(name="app.worker.tasks.expire_jobs")
def expire_jobs() -> int:
    from app.domains.ingestion import service as ingestion

    with get_sessionmaker()() as session:
        n = ingestion.expire_due_jobs(session)
    log.info("task_expire_jobs_done", expired=n)
    return n


@celery_app.task(name="app.worker.tasks.requeue_stale_resumes")
def requeue_stale_resumes() -> int:
    """Put lost resumes back on the queue: pending too long, or 'processing' with no live worker."""
    from app.domains.resumes.models import Resume

    cutoff = datetime.now(UTC) - STALE_AFTER
    with get_sessionmaker()() as session:
        stale = select(Resume.id).where(
            Resume.updated_at < cutoff,  # last touched: upload, or the claim into 'processing'
            or_(
                Resume.parsing_status == ResumeStatus.PENDING,
                Resume.parsing_status == ResumeStatus.PROCESSING,
            ),
        )
        ids = list(session.scalars(stale))
        if ids:
            # 'processing' rows can't be claimed again until they're pending.
            session.execute(
                update(Resume).where(Resume.id.in_(ids)).values(parsing_status=ResumeStatus.PENDING)
            )
            session.commit()
    for rid in ids:
        process_resume.delay(str(rid))
    if ids:
        log.warning("task_requeued_stale_resumes", count=len(ids))
    return len(ids)
