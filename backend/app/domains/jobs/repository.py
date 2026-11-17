"""Job listing queries with keyset pagination.

Why keyset instead of OFFSET: `OFFSET 10000` makes Postgres read and discard 10k rows, and
pages shift when new jobs are ingested between requests (items get skipped or repeated).
A keyset cursor "(listed_at, id) < (last_seen_listed_at, last_seen_id)" uses the index
ix_jobs_status_listed_at directly and stays stable under inserts.
"""

import base64
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, func, select, tuple_
from sqlalchemy.orm import Session, selectinload

from app.db.enums import EmploymentType, JobStatus, LocationType
from app.domains.jobs.models import Job, JobSkill


class InvalidCursorError(ValueError):
    pass


def encode_cursor(listed_at: datetime, job_id: uuid.UUID) -> str:
    raw = f"{listed_at.isoformat()}|{job_id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        ts, jid = base64.urlsafe_b64decode(padded).decode().split("|")
        return datetime.fromisoformat(ts), uuid.UUID(jid)
    except (ValueError, UnicodeDecodeError) as exc:
        raise InvalidCursorError("invalid cursor") from exc


@dataclass(frozen=True)
class JobListFilters:
    status: JobStatus = JobStatus.ACTIVE
    city: str | None = None
    location_type: LocationType | None = None
    employment_type: EmploymentType | None = None
    company: str | None = None


def list_jobs(
    session: Session, filters: JobListFilters, limit: int, cursor: str | None
) -> tuple[list[Job], str | None]:
    stmt: Select[Job] = select(Job).where(Job.status == filters.status)
    if filters.city:
        stmt = stmt.where(func.lower(Job.city) == filters.city.lower())
    if filters.location_type:
        stmt = stmt.where(Job.location_type == filters.location_type)
    if filters.employment_type:
        stmt = stmt.where(Job.employment_type == filters.employment_type)
    if filters.company:
        # autoescape: a user-typed "%" or "_" is matched literally, not as a wildcard.
        stmt = stmt.where(Job.company.icontains(filters.company, autoescape=True))
    if cursor:
        last_listed_at, last_id = decode_cursor(cursor)
        stmt = stmt.where(tuple_(Job.listed_at, Job.id) < tuple_(last_listed_at, last_id))

    rows = list(
        session.scalars(stmt.order_by(Job.listed_at.desc(), Job.id.desc()).limit(limit + 1))
    )
    # Fetch one extra row to know whether another page exists without a COUNT(*).
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = encode_cursor(rows[-1].listed_at, rows[-1].id) if has_more and rows else None
    return rows, next_cursor


def get_job_with_skills(session: Session, job_id: uuid.UUID) -> Job | None:
    return session.scalar(
        select(Job)
        .where(Job.id == job_id)
        .options(selectinload(Job.skills).joinedload(JobSkill.skill))
    )
