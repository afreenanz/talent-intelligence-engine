"""Candidate activity: search logs, impressions, clicks/dismissals, saved jobs, applications.

Rules
- Every state change also appends to the event log (job_interactions) in the SAME transaction,
  so state and history can't disagree.
- Save/unsave are idempotent: repeating them is safe, and only real changes are logged.
- Ownership is structural: every function takes the authenticated candidate_id.
"""

import base64
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.errors import AppError, ConflictError, NotFoundError
from app.db.enums import ApplicationStatus, InteractionType, JobStatus
from app.domains.interactions.models import Application, JobInteraction, SavedJob, SearchLog
from app.domains.jobs.models import Job

FEEDBACK_TYPES = {InteractionType.CLICK, InteractionType.DISMISS}

# Application lifecycle. Terminal states have no outgoing transitions.
ALLOWED_TRANSITIONS: dict[ApplicationStatus, set[ApplicationStatus]] = {
    ApplicationStatus.APPLIED: {
        ApplicationStatus.SCREENING,
        ApplicationStatus.REJECTED,
        ApplicationStatus.WITHDRAWN,
    },
    ApplicationStatus.SCREENING: {
        ApplicationStatus.INTERVIEWING,
        ApplicationStatus.REJECTED,
        ApplicationStatus.WITHDRAWN,
    },
    ApplicationStatus.INTERVIEWING: {
        ApplicationStatus.OFFER,
        ApplicationStatus.REJECTED,
        ApplicationStatus.WITHDRAWN,
    },
    ApplicationStatus.OFFER: {ApplicationStatus.WITHDRAWN},
    ApplicationStatus.REJECTED: set(),
    ApplicationStatus.WITHDRAWN: set(),
}


class JobUnavailableError(ConflictError):
    code = "job_unavailable"


def _job_or_404(session: Session, job_id: uuid.UUID, *, require_active: bool) -> Job:
    job = session.get(Job, job_id)
    if job is None:
        raise NotFoundError("Job not found")
    if require_active and job.status is not JobStatus.ACTIVE:
        raise JobUnavailableError(f"This job is no longer available ({job.status.value})")
    return job


def _refresh_derived(session: Session, candidate_id: uuid.UUID) -> None:
    """Recompute learned preferences right away, so the next search reflects this action.

    One aggregate query over this candidate's events; moves to a background worker in M9.
    """
    from app.domains.personalization.derived import recompute_derived_preferences

    recompute_derived_preferences(session, candidate_id)


def _log(
    session: Session,
    candidate_id: uuid.UUID,
    job_id: uuid.UUID,
    kind: InteractionType,
    search_log_id: uuid.UUID | None = None,
    position: int | None = None,
) -> None:
    session.add(
        JobInteraction(
            candidate_id=candidate_id,
            job_id=job_id,
            interaction_type=kind,
            search_log_id=search_log_id,
            position=position,
        )
    )


# ---------------------------------------------------------------- searches and impressions


def record_search(
    session: Session,
    candidate_id: uuid.UUID,
    *,
    query: str | None,
    filters: dict[str, Any],
    mode: str,
    ranking: str,
    job_ids: list[uuid.UUID],
    latency_ms: int,
) -> SearchLog:
    """One search_logs row plus one impression per returned job (with its 1-based position).

    Impressions are logged by the server, which knows exactly what it returned. That gives
    the denominator for click-through (needed to interpret clicks honestly in 5B).
    """
    log = SearchLog(
        candidate_id=candidate_id,
        query=query,
        filters=filters,
        mode=mode,
        ranking=ranking,
        result_count=len(job_ids),
        latency_ms=latency_ms,
    )
    session.add(log)
    session.flush()
    if job_ids:
        session.execute(
            insert(JobInteraction),
            [
                {
                    "candidate_id": candidate_id,
                    "job_id": jid,
                    "search_log_id": log.id,
                    "position": i,
                    "interaction_type": InteractionType.IMPRESSION,
                }
                for i, jid in enumerate(job_ids, start=1)
            ],
        )
    session.commit()
    return log


def recent_searches(session: Session, candidate_id: uuid.UUID, limit: int = 10) -> list[SearchLog]:
    return list(
        session.scalars(
            select(SearchLog)
            .where(SearchLog.candidate_id == candidate_id, SearchLog.query.is_not(None))
            .order_by(SearchLog.created_at.desc())
            .limit(limit)
        )
    )


def record_feedback(
    session: Session,
    candidate_id: uuid.UUID,
    job_id: uuid.UUID,
    kind: InteractionType,
    search_log_id: uuid.UUID | None,
    position: int | None,
) -> None:
    if kind not in FEEDBACK_TYPES:
        raise AppError("Use the saved-jobs and applications endpoints for saves and applications")
    _job_or_404(session, job_id, require_active=False)
    if search_log_id is not None:
        owner = session.scalar(select(SearchLog.candidate_id).where(SearchLog.id == search_log_id))
        if owner != candidate_id:  # someone else's (or a made-up) search: don't attribute it
            raise NotFoundError("Search not found")
    _log(session, candidate_id, job_id, kind, search_log_id, position)
    session.commit()
    _refresh_derived(session, candidate_id)


# ---------------------------------------------------------------- saved jobs


def save_job(session: Session, candidate_id: uuid.UUID, job_id: uuid.UUID) -> bool:
    """Returns True if newly saved, False if it was already saved (idempotent)."""
    _job_or_404(session, job_id, require_active=True)
    inserted = session.execute(
        insert(SavedJob)
        .values(candidate_id=candidate_id, job_id=job_id)
        .on_conflict_do_nothing()
        .returning(SavedJob.job_id)
    ).first()
    if inserted is not None:
        _log(session, candidate_id, job_id, InteractionType.SAVE)
    session.commit()
    _refresh_derived(session, candidate_id)
    return inserted is not None


def unsave_job(session: Session, candidate_id: uuid.UUID, job_id: uuid.UUID) -> None:
    removed = session.execute(
        delete(SavedJob)
        .where(SavedJob.candidate_id == candidate_id, SavedJob.job_id == job_id)
        .returning(SavedJob.job_id)
    ).first()
    if removed is not None:
        _log(session, candidate_id, job_id, InteractionType.UNSAVE)
    session.commit()
    _refresh_derived(session, candidate_id)


def _encode(ts: datetime, jid: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(f"{ts.isoformat()}|{jid}".encode()).decode().rstrip("=")


def _decode(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        ts, jid = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode().split("|")
        return datetime.fromisoformat(ts), uuid.UUID(jid)
    except (ValueError, UnicodeDecodeError) as exc:
        raise AppError("Invalid pagination cursor") from exc


def list_saved(
    session: Session, candidate_id: uuid.UUID, limit: int, cursor: str | None
) -> tuple[list[tuple[SavedJob, Job]], str | None]:
    stmt = (
        select(SavedJob, Job)
        .join(Job, Job.id == SavedJob.job_id)
        .where(SavedJob.candidate_id == candidate_id)
    )
    if cursor:
        ts, jid = _decode(cursor)
        stmt = stmt.where(tuple_(SavedJob.created_at, SavedJob.job_id) < tuple_(ts, jid))
    result = session.execute(
        stmt.order_by(SavedJob.created_at.desc(), SavedJob.job_id.desc()).limit(limit + 1)
    )
    rows = [(saved, job) for saved, job in result]
    more = len(rows) > limit
    rows = rows[:limit]
    nxt = _encode(rows[-1][0].created_at, rows[-1][0].job_id) if more and rows else None
    return rows, nxt


def saved_job_ids(
    session: Session, candidate_id: uuid.UUID, job_ids: list[uuid.UUID]
) -> set[uuid.UUID]:
    if not job_ids:
        return set()
    return set(
        session.scalars(
            select(SavedJob.job_id).where(
                SavedJob.candidate_id == candidate_id, SavedJob.job_id.in_(job_ids)
            )
        )
    )


# ---------------------------------------------------------------- applications


def apply(
    session: Session, candidate_id: uuid.UUID, job_id: uuid.UUID, notes: str | None
) -> Application:
    _job_or_404(session, job_id, require_active=True)
    exists = session.scalar(
        select(Application).where(
            Application.candidate_id == candidate_id, Application.job_id == job_id
        )
    )
    if exists is not None:
        raise ConflictError("You have already applied to this job")
    app_row = Application(
        candidate_id=candidate_id,
        job_id=job_id,
        notes=notes,
        application_status=ApplicationStatus.APPLIED,
    )
    session.add(app_row)
    _log(session, candidate_id, job_id, InteractionType.APPLY)
    session.commit()
    _refresh_derived(session, candidate_id)
    return app_row


def list_applications(session: Session, candidate_id: uuid.UUID) -> list[tuple[Application, Job]]:
    result = session.execute(
        select(Application, Job)
        .join(Job, Job.id == Application.job_id)
        .where(Application.candidate_id == candidate_id)
        .order_by(Application.updated_at.desc())
    )
    return [(application, job) for application, job in result]


def get_application(
    session: Session, candidate_id: uuid.UUID, application_id: uuid.UUID
) -> Application:
    row = session.scalar(
        select(Application).where(
            Application.id == application_id, Application.candidate_id == candidate_id
        )
    )
    if row is None:
        raise NotFoundError("Application not found")
    return row


def update_application(
    session: Session,
    candidate_id: uuid.UUID,
    application_id: uuid.UUID,
    status: ApplicationStatus | None,
    notes: str | None,
) -> Application:
    row = get_application(session, candidate_id, application_id)
    if status is not None and status is not row.application_status:
        allowed = ALLOWED_TRANSITIONS[row.application_status]
        if status not in allowed:
            raise ConflictError(
                f"Cannot change status from {row.application_status.value} to {status.value}",
                details={"allowed": sorted(s.value for s in allowed)},
            )
        row.application_status = status
    if notes is not None:
        row.notes = notes
    session.commit()
    return row
