import uuid

import pytest

from app.domains.search.fusion import reciprocal_rank_fusion

A, B, C, D = (uuid.UUID(int=i) for i in range(1, 5))


def test_rrf_matches_hand_computed_scores() -> None:
    fused = dict(reciprocal_rank_fusion({"lex": [A, B, C], "dense": [B, D]}, k=60))
    assert fused[A] == pytest.approx(1 / 61)
    assert fused[B] == pytest.approx(1 / 62 + 1 / 61)
    assert fused[C] == pytest.approx(1 / 63)
    assert fused[D] == pytest.approx(1 / 62)


def test_document_found_by_both_beats_single_list_winner() -> None:
    order = [d for d, _ in reciprocal_rank_fusion({"lex": [A, B], "dense": [B, C]})]
    assert order[0] == B


def test_weights_scale_contributions() -> None:
    fused = dict(reciprocal_rank_fusion({"lex": [A], "dense": [B]}, weights={"lex": 2.0}))
    assert fused[A] == pytest.approx(2 / 61) and fused[B] == pytest.approx(1 / 61)


def test_k_controls_consensus_vs_single_top_hit() -> None:
    # A is #1 in one list only; B is #4 in both lists.
    # B = 2/(k+4), A = 1/(k+1)  ->  B wins exactly when k > 2.
    # (Note: a doc at #2 in both lists beats a single #1 for *every* k > 0.)
    x1, x2, y1, y2 = (uuid.UUID(int=i) for i in range(10, 14))
    lists = {"lex": [A, x1, y1, B], "dense": [C, x2, y2, B]}
    assert reciprocal_rank_fusion(lists, k=60)[0][0] == B
    assert reciprocal_rank_fusion(lists, k=1)[0][0] in {A, C}


def test_ties_are_deterministic_and_empty_input_is_empty() -> None:
    assert reciprocal_rank_fusion({"x": [B], "y": [A]}) == reciprocal_rank_fusion(
        {"y": [A], "x": [B]}
    )
    assert reciprocal_rank_fusion({}) == []
    with pytest.raises(ValueError):
        reciprocal_rank_fusion({"x": [A]}, k=0)
