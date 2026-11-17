"""End-to-end ingestion behaviour against a real database."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.enums import IngestionMode, JobStatus, SkillImportance
from app.domains.ingestion import service
from app.domains.ingestion.models import IngestionError
from app.domains.jobs.models import Job, JobSkill
from app.domains.skills.seed import load_taxonomy, seed_skills

NOW = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
TAXONOMY = Path(__file__).resolve().parents[3] / "data" / "taxonomy" / "skills_v1.json"

DESC = (
    "Acme is a fintech company building payment products. We are hiring a Backend Engineer "
    "to design and build scalable REST services in Python with PostgreSQL and Kafka, "
    "own services end to end, and improve reliability and observability of core APIs."
)


@pytest.fixture(autouse=True)
def taxonomy(db_session: Session) -> None:
    seed_skills(db_session, load_taxonomy(TAXONOMY))


def job(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "external_id": "j-1",
        "title": "Backend Engineer",
        "company": "Acme Technologies Pvt Ltd",
        "description": DESC,
        "location": "Bangalore, India",
        "salary_text": "15-25 LPA",
        "experience_text": "2-5 years",
        "required_skills": ["Python", "postgres"],
        "preferred_skills": ["Kafka"],
        "posted_at": (NOW - timedelta(days=3)).isoformat(),
        "expires_at": (NOW + timedelta(days=30)).isoformat(),
    }
    base.update(overrides)
    return base


def run(session: Session, records: list[dict[str, Any]], **kw: Any) -> Any:
    return service.ingest(session, records, source=kw.pop("source", "test"), now=NOW, **kw)


def test_insert_normalizes_all_fields(db_session: Session) -> None:
    r = run(db_session, [job()])
    assert (r.inserted, r.failed) == (1, 0)
    j = db_session.scalar(select(Job))
    assert j is not None
    assert j.city == "Bengaluru" and j.country == "India"
    assert (j.salary_min, j.salary_max, j.salary_currency) == (1_500_000, 2_500_000, "INR")
    assert (j.experience_min, j.experience_max) == (2, 5)
    assert j.normalized_company == "acme technologies"
    assert j.status is JobStatus.ACTIVE
    assert j.listed_at == NOW - timedelta(days=3)


def test_skills_from_lists_and_text_with_importance(db_session: Session) -> None:
    run(db_session, [job()])
    rows = db_session.execute(
        select(JobSkill.importance, func.array_agg(JobSkill.skill_id)).group_by(JobSkill.importance)
    ).all()
    names = {
        imp: {
            s.skill.name
            for s in db_session.scalars(select(JobSkill).where(JobSkill.importance == imp))
        }
        for imp, _ in rows
    }
    assert names[SkillImportance.REQUIRED] == {"Python", "PostgreSQL"}  # alias "postgres" resolved
    assert names[SkillImportance.PREFERRED] == {"Kafka"}
    # "observability" appears in the text -> mentioned. "REST services" does NOT match the
    # "REST APIs" skill: the bare word "rest" is deliberately not used for text matching.
    assert names[SkillImportance.MENTIONED] == {"Observability"}


def test_reimport_is_idempotent(db_session: Session) -> None:
    records = [job(external_id=f"j-{i}", title=f"Backend Engineer {i}") for i in range(5)]
    run(db_session, records)
    second = run(db_session, records)
    assert (second.inserted, second.updated, second.unchanged) == (0, 0, 5)
    assert db_session.scalar(select(func.count()).select_from(Job)) == 5


def test_changed_record_is_updated_in_place(db_session: Session) -> None:
    run(db_session, [job()])
    original = db_session.scalar(select(Job))
    assert original is not None
    original_id, original_hash = original.id, original.content_hash

    r = run(db_session, [job(salary_text="20-30 LPA", required_skills=["Python", "Go"])])
    assert r.updated == 1
    db_session.expire_all()
    j = db_session.scalar(select(Job))
    assert j is not None
    assert j.id == original_id and j.content_hash != original_hash
    assert j.salary_min == 2_000_000
    assert {s.skill.name for s in j.skills if s.importance is SkillImportance.REQUIRED} == {
        "Python",
        "Go",
    }


def test_near_duplicate_from_another_source_is_linked_not_dropped(db_session: Session) -> None:
    run(db_session, [job()], source="feed_a")
    repost = job(
        external_id="other-77",
        company="ACME Technologies Private Limited",
        title="Backend Engineer",
        description=DESC + " Apply today.",
    )
    r = run(db_session, [repost], source="feed_b")
    assert r.duplicates == 1
    dup = db_session.scalar(select(Job).where(Job.source == "feed_b"))
    canonical = db_session.scalar(select(Job).where(Job.source == "feed_a"))
    assert dup is not None and canonical is not None
    assert dup.status is JobStatus.DUPLICATE and dup.duplicate_of_job_id == canonical.id


def test_same_title_different_city_is_not_a_duplicate(db_session: Session) -> None:
    run(db_session, [job()])
    r = run(db_session, [job(external_id="j-2", location="Pune")])
    assert (r.inserted, r.duplicates) == (1, 0)


def test_repost_after_original_expired_is_a_new_job(db_session: Session) -> None:
    old = job(
        posted_at=(NOW - timedelta(days=90)).isoformat(),
        expires_at=(NOW - timedelta(days=40)).isoformat(),
    )
    run(db_session, [old])
    r = run(db_session, [job(external_id="j-2")])  # posted 3 days ago, long after expiry
    assert (r.inserted, r.duplicates) == (1, 0)


def test_dissimilar_description_is_not_a_duplicate(db_session: Session) -> None:
    run(db_session, [job()])
    other = job(
        external_id="j-2",
        description="Totally different role focused on internal tooling, Go services, "
        "batch billing jobs and on-call ownership for the payments ledger.",
    )
    assert run(db_session, [other]).inserted == 1


def test_invalid_records_are_stored_with_payload_and_do_not_abort_batch(
    db_session: Session,
) -> None:
    records = [job(), {"external_id": "bad", "title": "X"}, job(external_id="j-2", location="Pune")]
    r = run(db_session, records)
    assert (r.received, r.inserted, r.failed) == (3, 2, 1)
    err = db_session.scalar(select(IngestionError))
    assert err is not None
    assert err.error_type == "validation" and err.retryable is False
    assert err.raw_record["external_id"] == "bad"


def test_past_expiry_is_inserted_as_expired_and_expiry_job_transitions(
    db_session: Session,
) -> None:
    r = run(
        db_session,
        [
            job(
                expires_at=(NOW - timedelta(days=1)).isoformat(),
                posted_at=(NOW - timedelta(days=30)).isoformat(),
            )
        ],
    )
    assert r.inserted == 1
    assert db_session.scalar(select(Job.status)) is JobStatus.EXPIRED

    run(
        db_session,
        [
            job(
                external_id="j-2",
                location="Pune",
                expires_at=(NOW + timedelta(hours=1)).isoformat(),
            )
        ],
    )
    assert service.expire_due_jobs(db_session, NOW + timedelta(hours=2)) == 1


def test_snapshot_mode_removes_unseen_jobs(db_session: Session) -> None:
    run(db_session, [job(), job(external_id="j-2", location="Pune")], source="feed")
    r = service.ingest(
        db_session,
        [job()],
        source="feed",
        mode=IngestionMode.SNAPSHOT,
        now=NOW + timedelta(hours=1),
    )
    assert r.removed == 1
    assert (
        db_session.scalar(select(Job.status).where(Job.external_id == "j-2")) is JobStatus.REMOVED
    )

    # It reappears in the next snapshot -> becomes active again.
    again = service.ingest(
        db_session,
        [job(), job(external_id="j-2", location="Pune")],
        source="feed",
        mode=IngestionMode.SNAPSHOT,
        now=NOW + timedelta(hours=2),
    )
    assert again.updated == 1
    assert db_session.scalar(select(Job.status).where(Job.external_id == "j-2")) is JobStatus.ACTIVE


def test_snapshot_safety_valve_skips_removal_when_file_is_mostly_broken(
    db_session: Session,
) -> None:
    run(db_session, [job(), job(external_id="j-2", location="Pune")], source="feed")
    broken = [{"external_id": f"b{i}"} for i in range(5)]
    r = service.ingest(
        db_session, broken, source="feed", mode=IngestionMode.SNAPSHOT, now=NOW + timedelta(hours=1)
    )
    assert r.removed == 0
    assert (
        db_session.scalar(
            select(func.count()).select_from(Job).where(Job.status == JobStatus.ACTIVE)
        )
        == 2
    )


def test_retry_resolves_errors_once_the_cause_is_fixed(db_session: Session) -> None:
    r = run(db_session, [job(description="too short")])
    err = db_session.scalar(select(IngestionError))
    assert err is not None and r.failed == 1

    # Not retryable by default (validation error), so nothing happens...
    assert service.retry_failed(db_session, r.id).received == 0
    # ...until the stored payload is corrected and an explicit full retry is requested.
    err.raw_record = {**err.raw_record, "description": DESC}
    db_session.flush()
    retry = service.retry_failed(db_session, r.id, include_non_retryable=True)
    assert (retry.received, retry.inserted) == (1, 1)
    db_session.refresh(err)
    assert err.resolved_at is not None and err.attempts == 2
