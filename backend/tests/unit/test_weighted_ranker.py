import pytest

from app.domains.ranking.cross_encoder import min_max
from app.domains.ranking.explain import explain
from app.domains.ranking.features import FEATURE_NAMES, FeatureVector, JobFacts
from app.domains.ranking.weighted import WeightedRanker


def test_default_weights_file_is_valid() -> None:
    r = WeightedRanker.from_file()
    assert r.version == "weighted_v1"
    assert sum(r.weights.values()) == pytest.approx(1.0)


@pytest.mark.parametrize(
    "weights",
    [
        {n: 0.1 for n in FEATURE_NAMES} | {"recency": 0.2},  # sums to 1.1
        {n: 0.1 for n in FEATURE_NAMES if n != "recency"},  # missing a feature
        {n: 0.1 for n in FEATURE_NAMES} | {"recency": -0.1, "salary_fit": 0.3},  # negative
    ],
)
def test_invalid_weights_rejected(weights: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        WeightedRanker(weights, "bad")


def test_score_is_sum_of_contributions() -> None:
    r = WeightedRanker({n: 0.1 for n in FEATURE_NAMES}, "uniform")
    fv = FeatureVector({n: (1.0 if i % 2 else 0.0) for i, n in enumerate(FEATURE_NAMES)})
    assert r.score(fv) == pytest.approx(sum(r.contributions(fv).values())) == pytest.approx(0.5)


def test_min_max() -> None:
    assert min_max([2.0, 4.0, 3.0]) == [0.0, 1.0, 0.5]
    assert min_max([1.0, 1.0]) == [0.5, 0.5]
    assert min_max([]) == []


def test_explanation_is_derived_from_features() -> None:
    job = JobFacts(required_skill_ids=frozenset({1, 2, 3}))
    fv = FeatureVector(
        {n: 0.5 for n in FEATURE_NAMES} | {"required_skill_coverage": 2 / 3, "experience_fit": 1.0},
        missing={"salary_fit", "location_fit"},
        matched_core=frozenset({1, 2}),
        missing_core=frozenset({3}),
    )
    contrib = {n: 0.0 for n in FEATURE_NAMES} | {"required_skill_coverage": 0.2}
    lines = explain(fv, contrib, job, {1: "Python", 2: "SQL", 3: "Kafka"}, has_candidate=True)
    assert "Matches 2 of 3 required skills (Python, SQL)" in lines
    assert "Missing: Kafka" in lines
    assert "Your experience is within the required range" in lines
    assert any(
        line.startswith("Not enough information to judge: location fit, salary fit")
        for line in lines
    )
    assert lines[-1] == "Biggest factor: required skill coverage"


def test_sigmoid_is_stable_and_flat_for_close_logits() -> None:
    from app.domains.ranking.cross_encoder import sigmoid

    assert sigmoid(0) == 0.5 and sigmoid(-1000) == 0.0 and sigmoid(1000) == 1.0
    # Regression: logits 6.37 vs 6.62 (observed live) must barely differ after normalisation.
    assert abs(sigmoid(6.62) - sigmoid(6.37)) < 0.001
