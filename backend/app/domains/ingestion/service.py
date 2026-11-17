"""Job ingestion pipeline: validate → normalize → identify → (dedup) → upsert → expire.

Guarantees
- Idempotent: re-importing an identical file changes nothing (every record is "unchanged").
- Incremental: only records whose content hash changed are written.
- Isolated failures: each record runs in its own SAVEPOINT; one bad record never aborts the
  batch. Failures are stored with the raw payload in `ingestion_errors` for retry.
- Bounded transactions: a commit every `batch_size` records, so a crash loses at most a batch
  (and re-running is safe because of idempotency).
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

import structlog
from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.enums import IngestionMode, IngestionRunStatus, JobStatus, SkillImportance
from app.domains.ingestion import normalize as norm
from app.domains.ingestion.models import IngestionError, IngestionRun
from app.domains.ingestion.schemas import JobRecordIn
from app.domains.jobs.models import Job, JobSkill
from app.domains.skills.extraction import SkillMatcher, build_matcher
from app.domains.skills.normalization import normalize_skill_name
from app.domains.skills.repository import resolve_or_create_skills

log = structlog.get_logger(__name__)

DEFAULT_DUPLICATE_THRESHOLD = 0.8  # Jaccard over 5-word shingles; see docs/ingestion.md
SNAPSHOT_MAX_FAILURE_RATIO = 0.1


class Outcome(StrEnum):
    INSERTED = "inserted"
    UPDATED = "updated"
    UNCHANGED = "unchanged"
    DUPLICATE = "duplicate"


@dataclass
class RecordFailure:
    error_type: str
    message: str
    retryable: bool
    external_id: str | None


@dataclass
class NormalizedJob:
    record: JobRecordIn
    fields: dict[str, Any]
    skills: dict[int, SkillImportance]
    content_hash: str
    skills_text: str = ""  # denormalised names for full-text search; not part of the hash
    warnings: list[str] = field(default_factory=list)


class JobIngestor:
    def __init__(
        self,
        session: Session,
        source: str,
        *,
        now: datetime | None = None,
        duplicate_threshold: float = DEFAULT_DUPLICATE_THRESHOLD,
        matcher: SkillMatcher | None = None,
    ) -> None:
        self.session = session
        self.source = source
        self.now = now or datetime.now(UTC)
        self.duplicate_threshold = duplicate_threshold
        self.matcher = matcher or build_matcher(session)

    # ------------------------------------------------------------------ per record

    def process(self, raw: dict[str, Any]) -> Outcome | RecordFailure:
        """Process one raw record inside a SAVEPOINT. Never raises for bad data."""
        external_id = str(raw.get("external_id") or "") or None
        if "__parse_error__" in raw:
            return RecordFailure("parse", str(raw["__parse_error__"]), False, None)
        try:
            record = JobRecordIn.model_validate(raw)
        except ValidationError as exc:
            msg = "; ".join(
                f"{'.'.join(map(str, e['loc'])) or 'record'}: {e['msg']}" for e in exc.errors()
            )
            return RecordFailure("validation", msg, False, external_id)

        try:
            with self.session.begin_nested():
                return self._upsert(self._normalize(record))
        except IntegrityError as exc:
            # A constraint we didn't anticipate in validation. Retrying won't help until fixed.
            return RecordFailure("database_constraint", str(exc.orig)[:500], False, external_id)
        except OperationalError as exc:
            return RecordFailure("database_unavailable", str(exc.orig)[:500], True, external_id)
        except SQLAlchemyError as exc:
            return RecordFailure("database", str(exc)[:500], True, external_id)

    def _normalize(self, rec: JobRecordIn) -> NormalizedJob:
        warnings: list[str] = []
        description = norm.clean_description(rec.description)
        loc = norm.parse_location(rec.location)

        if rec.salary_min is not None or rec.salary_max is not None:
            sal_min = norm.annualize(rec.salary_min, rec.salary_period)
            sal_max = norm.annualize(rec.salary_max, rec.salary_period)
            currency = rec.salary_currency.upper() if rec.salary_currency else None
        else:
            parsed = norm.parse_salary_text(rec.salary_text, rec.salary_currency)
            sal_min, sal_max, currency = parsed.minimum, parsed.maximum, parsed.currency
            if rec.salary_text and parsed.minimum is None:
                warnings.append(f"unparsed salary_text: {rec.salary_text!r}")

        if rec.experience_min is not None or rec.experience_max is not None:
            exp_min = Decimal(str(rec.experience_min)) if rec.experience_min is not None else None
            exp_max = Decimal(str(rec.experience_max)) if rec.experience_max is not None else None
        else:
            exp_min, exp_max = norm.parse_experience_text(rec.experience_text)
            if rec.experience_text and exp_min is None:
                warnings.append(f"unparsed experience_text: {rec.experience_text!r}")

        # Skills: explicit lists first (required beats preferred), then text mentions.
        explicit = resolve_or_create_skills(
            self.session, [*rec.required_skills, *rec.preferred_skills]
        )
        skills: dict[int, SkillImportance] = {}
        for name in rec.preferred_skills:
            skills[explicit[normalize_skill_name(name)].id] = SkillImportance.PREFERRED
        for name in rec.required_skills:
            skills[explicit[normalize_skill_name(name)].id] = SkillImportance.REQUIRED
        for skill_id in self.matcher.find(f"{rec.title}\n{description}"):
            skills.setdefault(skill_id, SkillImportance.MENTIONED)
        names = {s.id: s.name for s in explicit.values()} | self.matcher.names
        skills_text = " ".join(sorted(names[sid] for sid in skills if sid in names))

        fields: dict[str, Any] = {
            "title": rec.title,
            "normalized_title": norm.normalize_title(rec.title),
            "company": rec.company,
            "normalized_company": norm.normalize_company(rec.company),
            "description": description,
            "location": rec.location,
            "city": loc.city,
            "country": loc.country,
            "location_type": rec.location_type or loc.location_type,
            "employment_type": rec.employment_type,
            "salary_min": sal_min,
            "salary_max": sal_max,
            "salary_currency": currency if (sal_min or sal_max) else None,
            "experience_min": exp_min,
            "experience_max": exp_max,
            "posted_at": rec.posted_at,
            "expires_at": rec.expires_at,
        }
        hash_input = {
            **fields,
            "required": sorted(normalize_skill_name(s) for s in rec.required_skills),
            "preferred": sorted(normalize_skill_name(s) for s in rec.preferred_skills),
        }
        return NormalizedJob(
            rec, fields, skills, norm.content_hash(hash_input), skills_text, warnings
        )

    def _status_for(self, nj: NormalizedJob, duplicate_of: Any) -> JobStatus:
        expires_at = nj.fields["expires_at"]
        if duplicate_of is not None:
            return JobStatus.DUPLICATE
        if expires_at is not None and expires_at <= self.now:
            return JobStatus.EXPIRED
        return JobStatus.ACTIVE

    def _upsert(self, nj: NormalizedJob) -> Outcome:
        existing = self.session.scalar(
            select(Job).where(Job.source == self.source, Job.external_id == nj.record.external_id)
        )
        if existing is not None:
            existing.last_seen_at = self.now
            if existing.content_hash == nj.content_hash:
                if existing.status is JobStatus.REMOVED:  # reappeared in the feed
                    existing.status = self._status_for(nj, existing.duplicate_of_job_id)
                    return Outcome.UPDATED
                return Outcome.UNCHANGED
            for key, value in nj.fields.items():
                setattr(existing, key, value)
            existing.content_hash = nj.content_hash
            existing.skills_text = nj.skills_text
            existing.listed_at = nj.fields["posted_at"] or existing.first_seen_at
            existing.status = self._status_for(nj, existing.duplicate_of_job_id)
            self._replace_skills(existing, nj.skills)
            return Outcome.UPDATED

        canonical = self._find_duplicate(nj)
        job = Job(
            source=self.source,
            external_id=nj.record.external_id,
            content_hash=nj.content_hash,
            skills_text=nj.skills_text,
            listed_at=nj.fields["posted_at"] or self.now,
            first_seen_at=self.now,
            last_seen_at=self.now,
            duplicate_of_job_id=canonical.id if canonical else None,
            status=self._status_for(nj, canonical.id if canonical else None),
            **nj.fields,
        )
        job.skills = [JobSkill(skill_id=sid, importance=imp) for sid, imp in nj.skills.items()]
        self.session.add(job)
        self.session.flush()  # surface constraint errors inside this record's savepoint
        return Outcome.DUPLICATE if canonical else Outcome.INSERTED

    def _replace_skills(self, job: Job, wanted: dict[int, SkillImportance]) -> None:
        current = {js.skill_id: js for js in job.skills}
        for sid, js in current.items():
            if sid not in wanted:
                job.skills.remove(js)
        for sid, importance in wanted.items():
            if sid in current:
                current[sid].importance = importance
            else:
                job.skills.append(JobSkill(skill_id=sid, importance=importance))

    def _find_duplicate(self, nj: NormalizedJob) -> Job | None:
        """Near-duplicate = same company + normalized title + city + similar description,
        AND the two listings were live at the same time.

        Lifetime rule: a candidate counts if it is still active, or if the new posting was
        published before the candidate expired. A repost published *after* the original
        expired is a genuinely new opening, not a duplicate.
        """
        f = nj.fields
        candidates = self.session.scalars(
            select(Job).where(
                Job.normalized_company == f["normalized_company"],
                Job.normalized_title == f["normalized_title"],
                Job.city.is_not_distinct_from(f["city"]),
                Job.status.in_([JobStatus.ACTIVE, JobStatus.EXPIRED]),
                Job.duplicate_of_job_id.is_(None),
            )
        ).all()
        new_posted = f["posted_at"] or self.now
        mine = norm.shingles(f["description"])
        best, best_score = None, 0.0
        for cand in candidates:
            overlapping = cand.status is JobStatus.ACTIVE or (
                cand.expires_at is not None and new_posted <= cand.expires_at
            )
            if not overlapping:
                continue
            score = norm.jaccard(mine, norm.shingles(cand.description))
            if score > best_score:
                best, best_score = cand, score
        return best if best_score >= self.duplicate_threshold else None


# ---------------------------------------------------------------------- run orchestration


@dataclass
class RunSummary:
    run_id: str
    counts: dict[str, int]
    status: str


def ingest(
    session: Session,
    records: Iterable[dict[str, Any]],
    *,
    source: str,
    mode: IngestionMode = IngestionMode.INCREMENTAL,
    file_name: str | None = None,
    batch_size: int = 500,
    now: datetime | None = None,
    duplicate_threshold: float = DEFAULT_DUPLICATE_THRESHOLD,
) -> IngestionRun:
    now = now or datetime.now(UTC)
    run = IngestionRun(
        source=source,
        mode=mode,
        file_name=file_name,
        status=IngestionRunStatus.RUNNING,
        started_at=now,
    )
    session.add(run)
    session.commit()  # the run is visible (status=running) even if the import crashes

    ingestor = JobIngestor(session, source, now=now, duplicate_threshold=duplicate_threshold)
    try:
        for i, raw in enumerate(records, start=1):
            run.received += 1
            result = ingestor.process(raw)
            if isinstance(result, RecordFailure):
                run.failed += 1
                session.add(
                    IngestionError(
                        run_id=run.id,
                        source=source,
                        external_id=result.external_id,
                        raw_record=_jsonable(raw),
                        error_type=result.error_type,
                        error_message=result.message,
                        retryable=result.retryable,
                    )
                )
            else:
                _count(run, result)
            if i % batch_size == 0:
                session.commit()
                log.info("ingestion_batch_committed", run_id=str(run.id), processed=i)

        if mode is IngestionMode.SNAPSHOT:
            run.removed = _remove_unseen(session, run)
        run.expired = expire_due_jobs(session, now)
        run.status = IngestionRunStatus.COMPLETED
    except Exception as exc:
        session.rollback()
        run.status = IngestionRunStatus.FAILED
        run.error = f"{type(exc).__name__}: {exc}"[:2000]
        log.exception("ingestion_failed", run_id=str(run.id))
        raise
    finally:
        run.finished_at = datetime.now(UTC)
        session.add(run)
        session.commit()
        log.info("ingestion_finished", run_id=str(run.id), status=run.status.value, **_counts(run))
    return run


def _remove_unseen(session: Session, run: IngestionRun) -> int:
    """Snapshot mode: active jobs from this source not in the file are marked removed.

    Safety valve: a truncated or mostly-broken file would otherwise "remove" the whole feed.
    """
    if run.received == 0 or run.failed / run.received > SNAPSHOT_MAX_FAILURE_RATIO:
        log.warning(
            "snapshot_removal_skipped", run_id=str(run.id), received=run.received, failed=run.failed
        )
        return 0
    result = session.execute(
        update(Job)
        .where(
            Job.source == run.source,
            Job.status.in_([JobStatus.ACTIVE, JobStatus.DUPLICATE]),
            Job.last_seen_at < run.started_at,
        )
        .values(status=JobStatus.REMOVED, duplicate_of_job_id=None)
    )
    return int(result.rowcount)  # type: ignore[attr-defined]


def expire_due_jobs(session: Session, now: datetime | None = None) -> int:
    """Mark active jobs whose expires_at has passed. Safe to run any time (idempotent)."""
    result = session.execute(
        update(Job)
        .where(Job.status == JobStatus.ACTIVE, Job.expires_at <= (now or datetime.now(UTC)))
        .values(status=JobStatus.EXPIRED)
    )
    session.commit()
    return int(result.rowcount)  # type: ignore[attr-defined]


def retry_failed(
    session: Session, run_id: Any, *, include_non_retryable: bool = False
) -> IngestionRun:
    """Re-process unresolved failures of a run (e.g. after a DB outage or a parser fix)."""
    original = session.get(IngestionRun, run_id)
    if original is None:
        raise ValueError(f"ingestion run {run_id} not found")
    query = select(IngestionError).where(
        IngestionError.run_id == original.id, IngestionError.resolved_at.is_(None)
    )
    if not include_non_retryable:
        query = query.where(IngestionError.retryable.is_(True))
    errors = list(session.scalars(query))

    now = datetime.now(UTC)
    run = IngestionRun(
        source=original.source,
        mode=IngestionMode.INCREMENTAL,
        file_name=f"retry of {original.id}",
        status=IngestionRunStatus.RUNNING,
        started_at=now,
    )
    session.add(run)
    session.commit()
    ingestor = JobIngestor(session, original.source, now=now)
    for err in errors:
        run.received += 1
        result = ingestor.process(err.raw_record)
        err.attempts += 1
        if isinstance(result, RecordFailure):
            run.failed += 1
            err.error_type, err.error_message = result.error_type, result.message
            err.retryable = result.retryable
        else:
            err.resolved_at = now
            _count(run, result)
    run.status = IngestionRunStatus.COMPLETED
    run.finished_at = datetime.now(UTC)
    session.commit()
    return run


def _count(run: IngestionRun, outcome: Outcome) -> None:
    attr = {"duplicate": "duplicates"}.get(outcome.value, outcome.value)
    setattr(run, attr, getattr(run, attr) + 1)


def _counts(run: IngestionRun) -> dict[str, int]:
    names = (
        "received",
        "inserted",
        "updated",
        "unchanged",
        "duplicates",
        "failed",
        "expired",
        "removed",
    )
    return {n: getattr(run, n) for n in names}


def _jsonable(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        str(k): (v if isinstance(v, str | int | float | bool | list | dict | None) else str(v))
        for k, v in raw.items()
    }
