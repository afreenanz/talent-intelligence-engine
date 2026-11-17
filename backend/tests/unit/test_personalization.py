import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from app.db.enums import InteractionType as T
from app.db.enums import LocationType, MemoryType
from app.domains.personalization import derived
from app.domains.personalization.adjust import CAP, PersonalizationContext
from app.domains.personalization.categories import job_role_categories
from app.domains.ranking.features import CandidateFacts

NOW = datetime(2026, 11, 18, tzinfo=UTC)
J = [uuid.UUID(int=i) for i in range(1, 8)]
CATS = {
    J[0]: frozenset({"backend"}),
    J[1]: frozenset({"backend"}),
    J[2]: frozenset({"backend"}),
    J[3]: frozenset({"frontend"}),
    J[4]: frozenset({"frontend"}),
}


def ev(job: uuid.UUID, kind: T, days_ago: float = 0) -> tuple[uuid.UUID, T, datetime]:
    return job, kind, NOW - timedelta(days=days_ago)


@pytest.mark.parametrize(
    ("title", "skills", "expected"),
    [
        ("Senior Backend Engineer", [], {"backend"}),
        ("Full Stack Developer", [], {"fullstack", "backend", "frontend"}),
        ("Machine Learning Engineer", [], {"ml"}),
        ("SDET", [], {"qa"}),
        ("Software Engineer", ["frontend", "frontend", "backend"], {"frontend"}),  # skill fallback
        ("Software Engineer", ["frontend"], set()),  # too little evidence
        ("Accountant", [], set()),
    ],
)
def test_role_categories(title: str, skills: list[str], expected: set[str]) -> None:
    assert {c.value for c in job_role_categories(title, skills)} == expected


def test_bare_clicks_and_impressions_are_not_preference() -> None:
    scores, _ = derived.compute_category_scores(
        [ev(J[0], T.CLICK), ev(J[1], T.IMPRESSION), ev(J[3], T.IMPRESSION)], CATS, NOW
    )
    assert scores == {}


def test_click_confirmed_by_save_counts() -> None:
    scores, _ = derived.compute_category_scores([ev(J[0], T.CLICK), ev(J[0], T.SAVE)], CATS, NOW)
    assert scores["backend"] == pytest.approx(
        derived.EVENT_WEIGHTS[T.SAVE] + derived.CONFIRMED_CLICK_WEIGHT
    )


def test_one_contribution_per_job_per_type_and_negatives() -> None:
    scores, support = derived.compute_category_scores(
        [ev(J[3], T.DISMISS), ev(J[3], T.DISMISS), ev(J[4], T.DISMISS)], CATS, NOW
    )
    assert scores["frontend"] == pytest.approx(-4.0) and support["frontend"] == {J[3], J[4]}


def test_time_decay() -> None:
    fresh, _ = derived.compute_category_scores([ev(J[0], T.SAVE)], CATS, NOW)
    old, _ = derived.compute_category_scores([ev(J[0], T.SAVE, days_ago=30)], CATS, NOW)
    assert old["backend"] == pytest.approx(fresh["backend"] * 0.3679, abs=1e-3)


def _row(key: str, value: dict[str, object], explicit: bool, conf: float = 1.0) -> SimpleNamespace:
    t = MemoryType.EXPLICIT_PREFERENCE if explicit else MemoryType.DERIVED_PREFERENCE
    return SimpleNamespace(memory_key=key, memory_value=value, memory_type=t, confidence=conf)


def test_adjustment_is_capped_and_explained() -> None:
    ctx = PersonalizationContext.from_preferences(
        {
            "role_categories": _row(
                "role_categories", {"prefer": ["backend", "fullstack"], "avoid": []}, True
            ),
        }
    )  # type: ignore[arg-type]
    delta, reasons = ctx.adjustment(frozenset({"backend", "fullstack", "frontend"}), "Acme")
    assert delta == CAP  # 0.1 * (1 + 1) = 0.2 -> capped at 0.1
    assert "You prefer backend roles" in reasons


def test_derived_signals_are_weaker_and_say_so() -> None:
    ctx = PersonalizationContext.from_preferences(
        {
            "role_categories": _row(
                "role_categories", {"prefer": [], "avoid": ["frontend"]}, False, 0.45
            ),
            "company_avoid": _row("company_avoid", {"companies": ["Acme"]}, False, 0.33),
        }
    )  # type: ignore[arg-type]
    delta, reasons = ctx.adjustment(frozenset({"frontend"}), "ACME")
    assert delta == pytest.approx(-0.1 * (0.45 + 0.33))
    assert any(r.startswith("Based on your activity") for r in reasons)
    assert "You've dismissed jobs from this company before" in reasons


def test_explicit_preferences_override_profile_facts_but_derived_do_not() -> None:
    ctx = PersonalizationContext.from_preferences(
        {
            "location_type": _row("location_type", {"value": "remote"}, True),
            "min_salary": _row("min_salary", {"amount": 3_000_000, "currency": "INR"}, True),
            "employment_type": _row(
                "employment_type", {"value": "contract"}, False, 0.5
            ),  # derived: ignored
        }
    )  # type: ignore[arg-type]
    c = ctx.apply_to_candidate(CandidateFacts(min_salary=1_000_000, salary_currency="INR"))
    assert c.preferred_location_type is LocationType.REMOTE and c.min_salary == 3_000_000
    assert c.preferred_job_type is None


def test_empty_context_is_a_no_op() -> None:
    ctx = PersonalizationContext()
    assert ctx.is_empty and ctx.adjustment(frozenset({"backend"}), "Acme") == (0.0, [])


def _rj(i: int, cats: list[str]) -> Any:
    from app.domains.ranking.service import RankedJob

    return RankedJob(
        job_id=uuid.UUID(int=100 + i),
        title=f"j{i}",
        company="c",
        score=1 - i / 100,
        stage1_score=0,
        cross_encoder_score=None,
        features={},
        contributions={},
        missing_features=[],
        explanation=[],
        lexical_rank=None,
        semantic_rank=None,
        role_categories=cats,
    )


def test_exploration_inserts_unseen_categories_at_even_positions() -> None:
    from app.domains.ranking.service import _explore

    ranked = [_rj(i, ["data"]) for i in range(25)] + [
        _rj(30, ["backend"]),
        _rj(31, ["ml"]),
        _rj(32, ["backend"]),
    ]
    out = _explore(ranked, top_k=20, slots=2)
    head = out[:20]
    assert head[9].role_categories == ["backend"] and head[19].role_categories == ["ml"]
    assert head[9].exploration and head[19].exploration
    assert head[9].explanation[0].startswith("Exploring")
    assert len(out) == len(ranked) and len({r.job_id for r in out}) == len(ranked)  # nothing lost


def test_exploration_is_a_no_op_when_everything_is_already_represented() -> None:
    from app.domains.ranking.service import _explore

    ranked = [_rj(i, ["data"]) for i in range(30)]
    assert _explore(ranked, top_k=20, slots=2) == ranked


def test_preference_queries() -> None:
    ctx = PersonalizationContext.from_preferences(
        {
            "role_categories": _row(
                "role_categories", {"prefer": ["ml", "backend"], "avoid": ["qa"]}, True
            ),
        }
    )  # type: ignore[arg-type]
    assert ctx.preference_queries() == ["backend engineer", "machine learning engineer"]
