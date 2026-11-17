from app.domains.evaluation import agent_eval as ae


def test_arg_rules() -> None:
    assert ae._arg_ok("bengaluru", {"eq": "Bengaluru"})
    assert ae._arg_ok(2_000_000, {"gte": 1_500_000}) and not ae._arg_ok(None, {"gte": 1})
    assert ae._arg_ok(["backend", "data"], {"contains": "backend"})
    assert ae._get({"value": {"prefer": ["x"]}}, "value.prefer") == ["x"]


def _result(cid: str, passed: bool, infra: bool = False) -> ae.CaseResult:
    return ae.CaseResult(
        cid,
        "c",
        passed,
        {"no_error": not infra, "tools_required": passed},
        [],
        [],
        0,
        [],
        True,
        0,
        0,
        0,
        0,
        infra_error=infra,
    )


def test_summary_excludes_infra_errors_but_reports_them() -> None:
    s = ae.summarize([_result("a", True), _result("b", False), _result("c", False, infra=True)])
    assert s["cases"] == 3 and s["infra_errors_excluded"] == 1
    assert s["task_completion"] == 0.5  # 1 of the 2 cases that actually ran


def test_cost_estimate_uses_paid_tier_prices() -> None:
    r = _result("a", True)
    r.input_tokens, r.output_tokens = 1_000_000, 100_000
    assert ae.summarize([r])["estimated_cost_usd_paid_tier"] == round(0.30 + 0.25, 4)
