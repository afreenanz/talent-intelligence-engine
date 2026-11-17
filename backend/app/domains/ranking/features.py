"""Candidate-job compatibility features. Pure functions, no database access.

Every feature is in [0, 1]. When the data needed for a feature is missing, the feature is
NEUTRAL (0.5) and recorded in `missing`, so missing data is neither rewarded nor punished.
Each rule is a written, testable policy; the comments state the rationale.
"""

import math
from dataclasses import dataclass, field
from datetime import datetime

from app.db.enums import EmploymentType, LocationType

NEUTRAL = 0.5

FEATURE_NAMES = (
    "required_skill_coverage",
    "preferred_skill_coverage",
    "skill_jaccard",
    "semantic_similarity",
    "retrieval_score",
    "experience_fit",
    "salary_fit",
    "location_fit",
    "employment_type_match",
    "recency",
)


@dataclass(frozen=True)
class CandidateFacts:
    skill_ids: frozenset[int] = frozenset()
    experience_years: float | None = None
    city: str | None = None
    preferred_location_type: LocationType | None = None
    min_salary: int | None = None
    salary_currency: str | None = None
    preferred_job_type: EmploymentType | None = None


@dataclass(frozen=True)
class JobFacts:
    required_skill_ids: frozenset[int] = frozenset()
    preferred_skill_ids: frozenset[int] = frozenset()
    mentioned_skill_ids: frozenset[int] = frozenset()
    experience_min: float | None = None
    experience_max: float | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    city: str | None = None
    location_type: LocationType | None = None
    employment_type: EmploymentType | None = None
    listed_at: datetime | None = None

    @property
    def core_skill_ids(self) -> frozenset[int]:
        # Many postings list no explicit "required" skills. Then the skills mentioned in the
        # text are the best available stand-in for what the job needs.
        return self.required_skill_ids or self.mentioned_skill_ids

    @property
    def all_skill_ids(self) -> frozenset[int]:
        return self.required_skill_ids | self.preferred_skill_ids | self.mentioned_skill_ids


@dataclass
class FeatureVector:
    values: dict[str, float]
    missing: set[str] = field(default_factory=set)
    matched_core: frozenset[int] = frozenset()
    missing_core: frozenset[int] = frozenset()


EXPERIENCE_UNDER_DECAY_YEARS = 3.0  # 3+ years short of the minimum -> 0
EXPERIENCE_OVER_DECAY_YEARS = 10.0  # over-qualification is penalised more gently
RECENCY_TAU_DAYS = 30.0


def experience_fit(years: float | None, lo: float | None, hi: float | None) -> float | None:
    if years is None or (lo is None and hi is None):
        return None
    if lo is not None and years < lo:
        return max(0.0, 1 - (lo - years) / EXPERIENCE_UNDER_DECAY_YEARS)
    if hi is not None and years > hi:
        return max(0.0, 1 - (years - hi) / EXPERIENCE_OVER_DECAY_YEARS)
    return 1.0


def salary_fit(
    want: int | None, want_ccy: str | None, offer_max: int | None, offer_ccy: str | None
) -> float | None:
    if not want or offer_max is None or want_ccy is None or offer_ccy is None:
        return None
    if want_ccy != offer_ccy:
        return None  # not comparable without an exchange-rate policy (out of scope)
    return min(1.0, offer_max / want)


def location_fit(c: CandidateFacts, j: JobFacts) -> float | None:
    if j.location_type is LocationType.REMOTE:
        return 1.0 if c.preferred_location_type in (None, LocationType.REMOTE) else 0.8
    if c.preferred_location_type is LocationType.REMOTE and j.location_type is not None:
        return 0.2  # candidate wants remote; this job is onsite/hybrid
    if c.city is None or j.city is None:
        return None
    return 1.0 if c.city.lower() == j.city.lower() else 0.0


def employment_match(c: CandidateFacts, j: JobFacts) -> float | None:
    if c.preferred_job_type is None or j.employment_type is None:
        return None
    return 1.0 if c.preferred_job_type is j.employment_type else 0.0


def recency(listed_at: datetime | None, now: datetime) -> float | None:
    if listed_at is None:
        return None
    age_days = max(0.0, (now - listed_at).total_seconds() / 86400)
    return math.exp(-age_days / RECENCY_TAU_DAYS)


def _coverage(have: frozenset[int], need: frozenset[int]) -> float | None:
    return len(have & need) / len(need) if need else None


def compute_features(
    c: CandidateFacts,
    j: JobFacts,
    *,
    semantic_similarity: float | None,
    retrieval_score: float | None,
    now: datetime,
) -> FeatureVector:
    raw: dict[str, float | None] = {
        "required_skill_coverage": _coverage(c.skill_ids, j.core_skill_ids)
        if c.skill_ids
        else None,
        "preferred_skill_coverage": _coverage(c.skill_ids, j.preferred_skill_ids)
        if c.skill_ids
        else None,
        "skill_jaccard": (
            len(c.skill_ids & j.all_skill_ids) / len(c.skill_ids | j.all_skill_ids)
            if c.skill_ids and j.all_skill_ids
            else None
        ),
        "semantic_similarity": None
        if semantic_similarity is None
        else min(1.0, max(0.0, semantic_similarity)),
        "retrieval_score": retrieval_score,
        "experience_fit": experience_fit(c.experience_years, j.experience_min, j.experience_max),
        "salary_fit": salary_fit(c.min_salary, c.salary_currency, j.salary_max, j.salary_currency),
        "location_fit": location_fit(c, j),
        "employment_type_match": employment_match(c, j),
        "recency": recency(j.listed_at, now),
    }
    missing = {k for k, v in raw.items() if v is None}
    return FeatureVector(
        values={k: (NEUTRAL if v is None else float(v)) for k, v in raw.items()},
        missing=missing,
        matched_core=c.skill_ids & j.core_skill_ids,
        missing_core=j.core_skill_ids - c.skill_ids,
    )
