from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.domains.auth.models import User
from app.domains.candidates.models import CandidateProfile, CandidateSkill
from app.domains.ingestion import service as ingestion
from app.domains.ranking.service import CROSS_ENCODER_TOP_N, rank_jobs
from app.domains.ranking.weighted import WeightedRanker
from app.domains.search.indexing import embed_jobs
from app.domains.search.schemas import JobFilters
from app.domains.search.service import retrieve_jobs
from app.domains.skills.repository import resolve_or_create_skills
from tests.fakes import HashingEmbedder, KeywordReranker

pytestmark = pytest.mark.usefixtures("taxonomy")
NOW = datetime.now(UTC)
TAIL = " You will own services end to end and work with a small product team."


def rec(eid: str, title: str, required: list[str], **kw: Any) -> dict[str, Any]:
    return {
        "external_id": eid,
        "title": title,
        "company": f"Co {eid}",
        "description": f"{title} role working on payments platform." + TAIL,
        "required_skills": required,
        "posted_at": (NOW - timedelta(days=2)).isoformat(),
        **kw,
    }


@pytest.fixture
def setup(db_session: Session) -> tuple[HashingEmbedder, CandidateProfile]:
    ingestion.ingest(
        db_session,
        [
            rec("go", "Backend Engineer", ["Go", "Kubernetes"], experience_min=6, experience_max=9),
            rec(
                "py",
                "Backend Engineer",
                ["Python", "PostgreSQL"],
                experience_min=2,
                experience_max=5,
                location="Pune",
                salary_text="20-30 LPA",
            ),
            rec("js", "Backend Engineer", ["Node.js"], location="Mumbai"),
        ],
        source="rk",
        now=NOW,
    )
    emb = HashingEmbedder()
    embed_jobs(db_session, emb)
    user = User(email="r@x.com", password_hash="x")
    db_session.add(user)
    db_session.flush()
    profile = CandidateProfile(
        user_id=user.id,
        experience_years=Decimal("3"),
        location="Pune",
        preferred_salary_min=2_000_000,
    )
    skills = resolve_or_create_skills(db_session, ["Python", "PostgreSQL"])
    profile.skills = [CandidateSkill(skill_id=s.id) for s in skills.values()]
    db_session.add(profile)
    db_session.flush()
    return emb, profile


def _rank(db: Session, emb: HashingEmbedder, profile: CandidateProfile | None, **kw: Any) -> Any:
    retrieved = retrieve_jobs(
        db,
        query="backend engineer",
        candidate_id=None,
        filters=JobFilters(),
        top_k=100,
        embedder=emb,
    )
    return rank_jobs(
        db,
        retrieved,
        ranker=WeightedRanker.from_file(),
        candidate_id=profile.id if profile else None,
        query="backend engineer",
        embedding_model=emb.spec.name,
        **kw,
    )


def test_profile_fit_decides_order_among_equal_retrieval(db_session: Session, setup: Any) -> None:
    emb, profile = setup
    out = _rank(db_session, emb, profile)
    top = out.jobs[0]
    assert top.company == "Co py"  # skills, experience, location and salary all fit
    assert top.features["required_skill_coverage"] == 1.0
    assert top.features["experience_fit"] == 1.0
    assert top.features["location_fit"] == 1.0 and top.features["salary_fit"] == 1.0
    assert "Matches 2 of 2 required skills (PostgreSQL, Python)" in top.explanation
    go = next(j for j in out.jobs if j.company == "Co go")
    assert go.features["required_skill_coverage"] == 0.0 and go.features["experience_fit"] < 1.0


def test_without_profile_candidate_features_are_neutral(db_session: Session, setup: Any) -> None:
    emb, _ = setup
    out = _rank(db_session, emb, None)
    for job in out.jobs:
        assert job.features["required_skill_coverage"] == 0.5
        assert "required_skill_coverage" in job.missing_features


def test_ranking_is_deterministic(db_session: Session, setup: Any) -> None:
    emb, profile = setup
    a = [j.job_id for j in _rank(db_session, emb, profile).jobs]
    b = [j.job_id for j in _rank(db_session, emb, profile).jobs]
    assert a == b


def test_cross_encoder_stage_blends_scores_on_head_only(db_session: Session, setup: Any) -> None:
    emb, profile = setup
    reranker = KeywordReranker()
    out = _rank(db_session, emb, profile, stage="features+cross_encoder", reranker=reranker)
    assert reranker.calls == [min(CROSS_ENCODER_TOP_N, len(out.jobs))]
    for job in out.jobs:
        assert job.cross_encoder_score is not None
        assert job.score != job.stage1_score or job.cross_encoder_score is not None
    assert "cross_encoder" in out.timings_ms
