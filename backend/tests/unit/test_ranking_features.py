from datetime import UTC, datetime, timedelta

import pytest

from app.db.enums import EmploymentType, LocationType
from app.domains.ranking import features as f

NOW = datetime(2026, 11, 17, tzinfo=UTC)


@pytest.mark.parametrize(
    ("years", "lo", "hi", "expected"),
    [
        (3, 2, 5, 1.0),
        (2, 2, 5, 1.0),  # boundaries are inside
        (1, 2, 5, pytest.approx(2 / 3)),  # one year short of 3-year decay window
        (0, 5, 8, 0.0),  # 5 years short -> floor at 0
        (7, 2, 5, pytest.approx(0.8)),  # 2 years over a 10-year gentle decay
        (4, 2, None, 1.0),  # open-ended range
        (None, 2, 5, None),  # unknown candidate -> missing
        (3, None, None, None),  # unknown job requirement -> missing
    ],
)
def test_experience_fit(
    years: float | None, lo: float | None, hi: float | None, expected: object
) -> None:
    assert f.experience_fit(years, lo, hi) == expected


def test_salary_fit() -> None:
    assert f.salary_fit(2_000_000, "INR", 2_500_000, "INR") == 1.0
    assert f.salary_fit(2_000_000, "INR", 1_500_000, "INR") == 0.75
    assert f.salary_fit(2_000_000, "INR", 150_000, "USD") is None  # different currency
    assert f.salary_fit(None, "INR", 1_500_000, "INR") is None


def test_location_fit_rules() -> None:
    blr = f.CandidateFacts(city="Bengaluru")
    remote_seeker = f.CandidateFacts(city="Pune", preferred_location_type=LocationType.REMOTE)
    assert (
        f.location_fit(blr, f.JobFacts(city="bengaluru", location_type=LocationType.ONSITE)) == 1.0
    )
    assert f.location_fit(blr, f.JobFacts(city="Pune", location_type=LocationType.HYBRID)) == 0.0
    assert f.location_fit(blr, f.JobFacts(location_type=LocationType.REMOTE)) == 1.0
    assert (
        f.location_fit(remote_seeker, f.JobFacts(city="Pune", location_type=LocationType.ONSITE))
        == 0.2
    )
    assert f.location_fit(f.CandidateFacts(), f.JobFacts(city="Pune")) is None


def test_recency_decays_exponentially() -> None:
    assert f.recency(NOW, NOW) == 1.0
    assert f.recency(NOW - timedelta(days=30), NOW) == pytest.approx(0.3679, abs=1e-3)
    assert f.recency(None, NOW) is None


def test_skill_features_and_core_fallback() -> None:
    cand = f.CandidateFacts(skill_ids=frozenset({1, 2, 3}))
    job = f.JobFacts(required_skill_ids=frozenset({1, 2, 4}), preferred_skill_ids=frozenset({3, 5}))
    fv = f.compute_features(cand, job, semantic_similarity=0.7, retrieval_score=1.0, now=NOW)
    assert fv.values["required_skill_coverage"] == pytest.approx(2 / 3)
    assert fv.values["preferred_skill_coverage"] == pytest.approx(1 / 2)
    assert fv.values["skill_jaccard"] == pytest.approx(3 / 5)  # {1,2,3} vs {1,2,3,4,5}
    assert fv.matched_core == {1, 2} and fv.missing_core == {4}

    # No explicit required list: skills mentioned in the text stand in for "required".
    mention_only = f.JobFacts(mentioned_skill_ids=frozenset({2, 9}))
    fv2 = f.compute_features(
        cand, mention_only, semantic_similarity=None, retrieval_score=None, now=NOW
    )
    assert fv2.values["required_skill_coverage"] == 0.5


def test_missing_data_is_neutral_and_reported() -> None:
    fv = f.compute_features(
        f.CandidateFacts(), f.JobFacts(), semantic_similarity=None, retrieval_score=None, now=NOW
    )
    assert set(fv.values) == set(f.FEATURE_NAMES)
    assert all(v == f.NEUTRAL for v in fv.values.values())
    assert fv.missing == set(f.FEATURE_NAMES)


def test_employment_match() -> None:
    c = f.CandidateFacts(preferred_job_type=EmploymentType.FULL_TIME)
    assert f.employment_match(c, f.JobFacts(employment_type=EmploymentType.FULL_TIME)) == 1.0
    assert f.employment_match(c, f.JobFacts(employment_type=EmploymentType.CONTRACT)) == 0.0
    assert f.employment_match(c, f.JobFacts()) is None


def test_semantic_similarity_is_clipped() -> None:
    fv = f.compute_features(
        f.CandidateFacts(), f.JobFacts(), semantic_similarity=-0.2, retrieval_score=None, now=NOW
    )
    assert fv.values["semantic_similarity"] == 0.0


def test_known_but_unmatched_skills_score_zero_not_neutral() -> None:
    job = f.JobFacts(required_skill_ids=frozenset({1, 2}))
    unknown = f.compute_features(
        f.CandidateFacts(), job, semantic_similarity=None, retrieval_score=None, now=NOW
    )
    known_none = f.compute_features(
        f.CandidateFacts(skills_known=True),
        job,
        semantic_similarity=None,
        retrieval_score=None,
        now=NOW,
    )
    assert unknown.values["required_skill_coverage"] == 0.5
    assert known_none.values["required_skill_coverage"] == 0.0
    assert "required_skill_coverage" not in known_none.missing
