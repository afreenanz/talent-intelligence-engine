"""Stage 3: bounded personalisation of an already-ranked list.

    final = ranking_score + clip(ALPHA * match, -CAP, +CAP)
    match = Σ confidence over preferred categories the job has
          - Σ confidence over avoided categories the job has
          - confidence if the company is on the avoid list

The cap is the safety property: personalisation can re-order jobs of similar relevance, but
it can never lift an irrelevant job above a clearly relevant one (scores live in [0, 1]).
Explicit preferences (confidence 1.0) also *override* the matching profile facts (salary,
work mode, job type), because a stated preference is more current than a profile field.
"""

from dataclasses import dataclass, field, replace
from typing import Any

from app.db.enums import EmploymentType, LocationType, MemoryType
from app.domains.preferences.models import AgentMemory
from app.domains.ranking.features import CandidateFacts

ALPHA = 0.1
CAP = 0.1

# Search terms per role category, used as an extra retrieval channel so preferred kinds of job
# enter the candidate pool at all (re-ranking alone can't surface jobs retrieval never returned).
CATEGORY_QUERIES = {
    "backend": "backend engineer",
    "frontend": "frontend engineer",
    "fullstack": "full stack",
    "data": "data engineer",
    "ml": "machine learning engineer",
    "devops": "devops engineer",
    "mobile": "mobile android ios developer",
    "qa": "qa test automation",
    "security": "security",
    "design": "designer",
    "product": "product manager",
}


@dataclass(frozen=True)
class Signal:
    confidence: float
    explicit: bool


@dataclass
class PersonalizationContext:
    prefer: dict[str, Signal] = field(default_factory=dict)
    avoid: dict[str, Signal] = field(default_factory=dict)
    avoid_companies: dict[str, Signal] = field(default_factory=dict)
    overrides: dict[str, Any] = field(default_factory=dict)
    extra_skill_ids: frozenset[int] = frozenset()

    @property
    def is_empty(self) -> bool:
        return not (
            self.prefer
            or self.avoid
            or self.avoid_companies
            or self.overrides
            or self.extra_skill_ids
        )

    @classmethod
    def from_preferences(
        cls, effective: dict[str, AgentMemory], skill_ids_by_name: dict[str, int] | None = None
    ) -> "PersonalizationContext":
        ctx = cls()
        for key, row in effective.items():
            sig = Signal(row.confidence, row.memory_type is MemoryType.EXPLICIT_PREFERENCE)
            v = row.memory_value
            if key == "role_categories":
                ctx.prefer = {c: sig for c in v.get("prefer", [])}
                ctx.avoid = {c: sig for c in v.get("avoid", [])}
            elif key == "company_avoid":
                ctx.avoid_companies = {c.lower(): sig for c in v.get("companies", [])}
            elif sig.explicit and key == "min_salary":
                ctx.overrides["min_salary"] = int(v["amount"])
                ctx.overrides["salary_currency"] = v.get("currency", "INR")
            elif sig.explicit and key == "location_type":
                ctx.overrides["preferred_location_type"] = LocationType(v["value"])
            elif sig.explicit and key == "employment_type":
                ctx.overrides["preferred_job_type"] = EmploymentType(v["value"])
            elif sig.explicit and key == "locations" and v.get("cities"):
                ctx.overrides["city"] = v["cities"][0]
            elif sig.explicit and key == "skills_to_use" and skill_ids_by_name:
                ctx.extra_skill_ids = frozenset(
                    skill_ids_by_name[s.lower()]
                    for s in v.get("skills", [])
                    if s.lower() in skill_ids_by_name
                )
        return ctx

    def preference_queries(self) -> list[str]:
        return [CATEGORY_QUERIES[c] for c in sorted(self.prefer) if c in CATEGORY_QUERIES]

    def apply_to_candidate(self, c: CandidateFacts) -> CandidateFacts:
        updated = replace(c, **self.overrides) if self.overrides else c
        if self.extra_skill_ids:
            updated = replace(updated, skill_ids=updated.skill_ids | self.extra_skill_ids)
        return updated

    def adjustment(self, categories: frozenset[str], company: str) -> tuple[float, list[str]]:
        match = 0.0
        reasons: list[str] = []
        for cat in sorted(categories):
            if cat in self.prefer:
                s = self.prefer[cat]
                match += s.confidence
                reasons.append(
                    f"You prefer {cat} roles"
                    if s.explicit
                    else f"Based on your activity, you seem to like {cat} roles"
                )
            if cat in self.avoid:
                s = self.avoid[cat]
                match -= s.confidence
                reasons.append(
                    f"You asked to avoid {cat} roles"
                    if s.explicit
                    else f"Based on your activity, you seem less interested in {cat} roles"
                )
        sig = self.avoid_companies.get(company.lower())
        if sig is not None:
            match -= sig.confidence
            reasons.append(
                "You asked to avoid this company"
                if sig.explicit
                else "You've dismissed jobs from this company before"
            )
        return max(-CAP, min(CAP, ALPHA * match)), reasons
