import uuid

from app.domains.evaluation.retrieval_eval import (
    Config,
    ConfigResult,
    paired_bootstrap,
    score_query,
)
from scripts.build_retrieval_qrels import grade

A, B, C = (uuid.UUID(int=i) for i in range(1, 4))


def _result(name: str, values: dict[str, float]) -> ConfigResult:
    return ConfigResult(
        Config(name, "lexical", "m"), {q: {"ndcg@10": v} for q, v in values.items()}
    )


def test_score_query_returns_all_metrics() -> None:
    s = score_query([A, B], {A: 3, C: 2})
    assert set(s) == {"ndcg@10", "ndcg@5", "mrr@10", "p@5", "p@10", "recall@10", "recall@100"}
    assert s["mrr@10"] == 1.0 and s["recall@10"] == 0.5


def test_paired_bootstrap_is_deterministic_and_detects_consistent_gain() -> None:
    base = _result("a", {f"q{i}": 0.5 for i in range(20)})
    better = _result("b", {f"q{i}": 0.6 for i in range(20)})
    d, lo, hi = paired_bootstrap(base, better, "ndcg@10")
    assert round(d, 6) == 0.1 and lo > 0  # every query improved -> CI excludes 0
    assert paired_bootstrap(base, better, "ndcg@10") == (d, lo, hi)  # seeded


def test_paired_bootstrap_interval_spans_zero_for_noise() -> None:
    base = _result("a", {f"q{i}": 0.5 for i in range(20)})
    noisy = _result("b", {f"q{i}": 0.5 + (0.2 if i % 2 else -0.2) for i in range(20)})
    _, lo, hi = paired_bootstrap(base, noisy, "ndcg@10")
    assert lo < 0 < hi


def _job(family: str, skills: list[str], location: str, seniority: str = "mid") -> dict:  # type: ignore[type-arg]
    return {
        "location": location,
        "truth": {
            "role_family": family,
            "seniority": seniority,
            "required": skills,
            "preferred": [],
        },
    }


def test_silver_grade_rules() -> None:
    spec = {
        "families": ["backend"],
        "skills_any": ["Python"],
        "city": "Pune",
        "seniority": None,
        "remote": False,
    }
    assert grade(spec, _job("backend", ["Python"], "Pune")) == 3  # all conditions
    assert grade(spec, _job("backend", ["Python"], "Chennai")) == 2  # some conditions
    assert grade(spec, _job("backend", ["Java"], "Chennai")) == 1  # family only
    assert grade(spec, _job("frontend", ["Python"], "Pune")) == 0  # wrong family
    family_only = {**spec, "skills_any": [], "city": None}
    assert grade(family_only, _job("backend", [], "Chennai")) == 3
