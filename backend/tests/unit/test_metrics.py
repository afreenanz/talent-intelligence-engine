"""Every expected value here was computed by hand (shown in comments)."""

import math

import pytest

from app.domains.evaluation import metrics as m

# Ranked list and graded judgments (grade >= 2 counts as relevant for binary metrics).
RANKED = ["a", "b", "c", "d", "e"]
J = {"a": 3, "c": 2, "e": 1, "z": 3}  # z is relevant but never retrieved


def test_precision_at_k() -> None:
    assert m.precision_at_k(RANKED, J, 1) == 1.0  # a
    assert m.precision_at_k(RANKED, J, 3) == pytest.approx(2 / 3)  # a, c
    assert m.precision_at_k(RANKED, J, 5) == pytest.approx(2 / 5)  # e is grade 1 -> not relevant
    assert m.precision_at_k(["a"], J, 10) == pytest.approx(1 / 10)  # short list still divides by k


def test_recall_at_k_counts_unretrieved_relevant() -> None:
    assert m.recall_at_k(RANKED, J, 3) == pytest.approx(2 / 3)  # relevant = {a, c, z}
    assert m.recall_at_k(RANKED, J, 1) == pytest.approx(1 / 3)


def test_reciprocal_rank() -> None:
    assert m.reciprocal_rank(RANKED, J) == 1.0
    assert m.reciprocal_rank(["b", "c"], J) == 0.5
    assert m.reciprocal_rank(["b", "d", "e"], J) == 0.0  # e is only grade 1
    assert m.reciprocal_rank(["b", "d", "c"], J, k=2) == 0.0


def test_ndcg_hand_computed() -> None:
    # DCG@3 for gains [3,0,2] = 7/log2(2) + 0 + 3/log2(4) = 7 + 1.5 = 8.5
    # IDCG@3 over ideal [3,3,2] = 7 + 7/log2(3) + 3/2
    idcg = 7 + 7 / math.log2(3) + 1.5
    assert m.ndcg_at_k(RANKED, J, 3) == pytest.approx(8.5 / idcg)


def test_ndcg_perfect_and_zero() -> None:
    assert m.ndcg_at_k(["a", "z", "c", "e"], J, 4) == pytest.approx(1.0)
    assert m.ndcg_at_k(["b", "d"], J, 2) == 0.0


def test_ndcg_rewards_better_ordering() -> None:
    assert m.ndcg_at_k(["c", "a"], J, 2) < m.ndcg_at_k(["a", "c"], J, 2)


def test_undefined_cases_raise() -> None:
    with pytest.raises(ValueError):
        m.recall_at_k(RANKED, {"x": 1}, 5)
    with pytest.raises(ValueError):
        m.ndcg_at_k(RANKED, {}, 5)
    with pytest.raises(ValueError):
        m.precision_at_k(RANKED, J, 0)


def test_validate_judgments() -> None:
    assert m.validate_judgments({"q1": J}) == []
    problems = m.validate_judgments({"q1": {"x": 1}, "q2": {"x": 7}})
    assert problems == ["q1: no document with grade >= 2", "q2: grades out of range [7]"]


def test_average_precision_hand_computed() -> None:
    # relevant = {a, c, z}; hits at ranks 1 (a) and 3 (c): AP = (1/1 + 2/3) / 3
    assert m.average_precision(RANKED, J) == pytest.approx((1 + 2 / 3) / 3)
    assert m.average_precision(["a", "c", "z"], J) == pytest.approx(1.0)
    assert m.average_precision(["b", "d"], J) == 0.0
    assert m.average_precision(RANKED, J, k=1) == pytest.approx(1 / 3)
