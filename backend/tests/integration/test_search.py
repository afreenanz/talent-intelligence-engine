"""Retrieval against a real Postgres with pgvector, using the deterministic HashingEmbedder."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.candidates.models import CandidateProfile
from app.domains.ingestion import service as ingestion
from app.domains.jobs.models import Job
from app.domains.search.indexing import candidate_vector, embed_jobs
from app.domains.search.models import CandidateEmbedding, JobEmbedding
from app.domains.search.schemas import JobFilters
from app.domains.search.service import EmptySearchError, retrieve_jobs
from app.domains.skills.repository import resolve_or_create_skills
from tests.fakes import HashingEmbedder

pytestmark = pytest.mark.usefixtures("taxonomy")
NOW = datetime.now(UTC)
FILLER = " The team values ownership, testing and clear written communication."


def rec(eid: str, title: str, desc: str, **kw: Any) -> dict[str, Any]:
    return {
        "external_id": eid,
        "title": title,
        "company": f"Co {eid}",
        "description": desc + FILLER,
        "posted_at": (NOW - timedelta(days=1)).isoformat(),
        **kw,
    }


@pytest.fixture
def corpus(db_session: Session) -> HashingEmbedder:
    ingestion.ingest(
        db_session,
        [
            rec("t", "Python Developer", "Build internal tools.", location="Pune"),
            rec(
                "d",
                "Backend Engineer",
                "You will write Python services and APIs.",
                location="Pune",
                salary_text="10-15 LPA",
            ),
            rec(
                "k",
                "DevOps Engineer",
                "Kubernetes clusters, Terraform and Docker.",
                location="Bengaluru",
                salary_text="30-40 LPA",
            ),
            rec(
                "f",
                "Frontend Engineer",
                "React and TypeScript user interfaces.",
                location="Remote (India)",
            ),
            rec(
                "x",
                "Data Engineer",
                "Spark pipelines.",
                location="Pune",
                experience_min=8,
                experience_max=12,
                expires_at=(NOW - timedelta(days=1)).isoformat(),
                posted_at=(NOW - timedelta(days=40)).isoformat(),
            ),
        ],
        source="t",
        now=NOW,
    )
    emb = HashingEmbedder()
    embed_jobs(db_session, emb)
    return emb


def titles(
    session: Session, emb: HashingEmbedder, q: str, mode: str = "hybrid", **f: Any
) -> list[str]:
    r = retrieve_jobs(
        session,
        query=q,
        candidate_id=None,
        filters=JobFilters(**f),
        top_k=10,
        embedder=emb,
        mode=mode,
    )  # type: ignore[arg-type]
    return [j.title for j in r.jobs]


def test_lexical_uses_or_semantics_and_title_weight(
    db_session: Session, corpus: HashingEmbedder
) -> None:
    got = titles(db_session, corpus, "python developer kubernetes", mode="lexical")
    assert got[0] == "Python Developer"  # title (weight A) beats description-only mentions
    assert "DevOps Engineer" in got  # OR: matching only "kubernetes" is still retrieved


def test_lexical_stemming(db_session: Session, corpus: HashingEmbedder) -> None:
    assert "DevOps Engineer" in titles(db_session, corpus, "cluster", mode="lexical")


def test_stopword_only_query_returns_nothing_not_error(
    db_session: Session, corpus: HashingEmbedder
) -> None:
    assert titles(db_session, corpus, "the and of", mode="lexical") == []


def test_expired_jobs_are_never_retrieved(db_session: Session, corpus: HashingEmbedder) -> None:
    for mode in ("lexical", "dense", "hybrid"):
        assert "Data Engineer" not in titles(db_session, corpus, "spark pipelines data", mode=mode)


def test_filters_apply_to_every_mode(db_session: Session, corpus: HashingEmbedder) -> None:
    for mode in ("lexical", "dense", "hybrid"):
        got = titles(db_session, corpus, "engineer python kubernetes react", mode=mode, city="pune")
        assert set(got) <= {"Python Developer", "Backend Engineer"}, (mode, got)


def test_salary_filter_keeps_unknown_drops_known_lower(
    db_session: Session, corpus: HashingEmbedder
) -> None:
    got = titles(db_session, corpus, "engineer developer", mode="lexical", min_salary=2_000_000)
    assert "Backend Engineer" not in got  # known 10-15 LPA < 20 LPA
    assert "DevOps Engineer" in got  # known 30-40 LPA
    assert "Python Developer" in got  # salary unknown -> kept
    other = titles(
        db_session, corpus, "engineer", mode="lexical", min_salary=1, salary_currency="USD"
    )
    assert "DevOps Engineer" not in other  # INR salary is not comparable with a USD filter


def test_hybrid_reports_both_ranks(db_session: Session, corpus: HashingEmbedder) -> None:
    r = retrieve_jobs(
        db_session,
        query="python services",
        candidate_id=None,
        filters=JobFilters(),
        top_k=5,
        embedder=corpus,
    )
    top = r.jobs[0]
    assert top.lexical_rank is not None and top.semantic_rank is not None
    assert r.jobs == sorted(r.jobs, key=lambda j: -j.fused_score)


def test_embedding_is_incremental(db_session: Session, corpus: HashingEmbedder) -> None:
    again = embed_jobs(db_session, corpus)
    assert (again.embedded, again.skipped_unchanged) == (0, 4)

    job = db_session.scalar(select(Job).where(Job.external_id == "f"))
    assert job is not None
    job.description = "Vue and Svelte interfaces." + FILLER
    db_session.flush()
    changed = embed_jobs(db_session, corpus)
    assert changed.embedded == 1
    assert (
        db_session.scalar(select(func.count()).select_from(JobEmbedding)) == 4
    )  # upsert, not insert


def test_empty_query_without_profile_is_an_error(
    db_session: Session, corpus: HashingEmbedder
) -> None:
    with pytest.raises(EmptySearchError):
        retrieve_jobs(
            db_session,
            query="  ",
            candidate_id=None,
            filters=JobFilters(),
            top_k=5,
            embedder=corpus,
        )


def _profile(db_session: Session, skills: list[str], summary: str | None) -> CandidateProfile:
    from app.domains.auth.models import User
    from app.domains.candidates.models import CandidateSkill

    user = User(email=f"{len(skills)}-{summary}@x.com", password_hash="x")
    db_session.add(user)
    db_session.flush()
    profile = CandidateProfile(user_id=user.id, profile_summary=summary)
    resolved = resolve_or_create_skills(db_session, skills)
    profile.skills = [CandidateSkill(skill_id=s.id) for s in resolved.values()]
    db_session.add(profile)
    db_session.flush()
    db_session.refresh(profile)
    return profile


def test_profile_mode_uses_candidate_vector_and_skills(
    db_session: Session, corpus: HashingEmbedder
) -> None:
    profile = _profile(db_session, ["Kubernetes", "Terraform"], "Infrastructure engineer")
    r = retrieve_jobs(
        db_session,
        query=None,
        candidate_id=profile.id,
        filters=JobFilters(),
        top_k=3,
        embedder=corpus,
    )
    assert r.used_candidate_vector and r.lexical_query and "Kubernetes" in r.lexical_query
    assert r.jobs[0].title == "DevOps Engineer"


def test_candidate_vector_is_cached_until_profile_changes(
    db_session: Session, corpus: HashingEmbedder
) -> None:
    profile = _profile(db_session, ["Python"], "Backend developer")
    corpus.calls = 0
    candidate_vector(db_session, profile, corpus)
    candidate_vector(db_session, profile, corpus)
    assert corpus.calls == 1  # second call served from candidate_embeddings
    profile.profile_summary = "Data engineer"
    db_session.flush()
    candidate_vector(db_session, profile, corpus)
    assert corpus.calls == 2
    assert db_session.scalar(select(func.count()).select_from(CandidateEmbedding)) == 1


def test_cold_start_profile_has_no_vector(db_session: Session, corpus: HashingEmbedder) -> None:
    profile = _profile(db_session, [], None)
    assert candidate_vector(db_session, profile, corpus) is None
    with pytest.raises(EmptySearchError, match="profile is empty"):
        retrieve_jobs(
            db_session,
            query=None,
            candidate_id=profile.id,
            filters=JobFilters(),
            top_k=3,
            embedder=corpus,
        )


def test_extra_lexical_channel_widens_the_candidate_pool(
    db_session: Session, corpus: HashingEmbedder
) -> None:
    retrieve_jobs(  # baseline call: must not error without extra channels
        db_session,
        query="python services",
        candidate_id=None,
        filters=JobFilters(),
        top_k=10,
        embedder=corpus,
        mode="hybrid",
    )
    widened = retrieve_jobs(
        db_session,
        query="python services",
        candidate_id=None,
        filters=JobFilters(),
        top_k=10,
        embedder=corpus,
        mode="hybrid",
        extra_lexical_queries=["react typescript"],
    )
    assert "Frontend Engineer" in [j.title for j in widened.jobs]
    assert any(k.startswith("preference_channel") for k in widened.timings_ms)
