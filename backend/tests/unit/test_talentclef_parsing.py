from pathlib import Path

import numpy as np

from app.domains.evaluation import talentclef as tc
from app.domains.evaluation.ltr import lambdamart_leave_one_query_out

JOB = """Cashier

About the Role
Serve customers at the till. At least 2 years of retail experience preferred.

About Required Skills:
The following core competencies apply:
- Cash Handling
- POS Systems Operation
- Cash Handling

What We Offer
- Friendly team
"""

CV = """Jane Doe

PROFESSIONAL EXPERIENCE

Cashier, ShopCo
January 2020 – December 2021
Senior Cashier, MartCo
Jan 2022 - Present

EDUCATION
BA, City College
September 2014 – June 2018
"""


def test_required_skills_skip_intro_line_dedupe_and_stop_at_next_section() -> None:
    assert tc.parse_required_skills(JOB) == ("Cash Handling", "POS Systems Operation")


def test_experience_requirement() -> None:
    assert tc.parse_experience_requirement(JOB) == 2.0
    assert tc.parse_experience_requirement("No requirement stated.") is None


def test_resume_experience_ignores_education_dates_and_handles_present() -> None:
    # Jan 2020 - Apr 2026 (reference date) contiguous = 76 months = 6.3 years; 2014-2018 excluded.
    assert tc.parse_resume_experience(CV) == 6.3
    assert tc.parse_resume_experience("SKILLS\nPython") is None


def test_load_reads_queries_corpus_and_positive_qrels(tmp_path: Path) -> None:
    base = tmp_path / "TaskA" / "development" / "en"
    (base / "queries").mkdir(parents=True)
    (base / "corpus").mkdir()
    (base / "queries" / "1").write_text(JOB)
    (base / "corpus" / "10").write_text(CV)
    (base / "corpus" / "11").write_text("Other person")
    (base / "qrels.tsv").write_text("1\t0\t10\t1\n1\t0\t11\t0\n")
    ds = tc.load(tmp_path)
    assert set(ds.jobs) == {"1"} and set(ds.resumes) == {"10", "11"}
    assert ds.qrels == {"1": {"10": 1}}  # zero-grade rows are not positives


def test_lambdamart_runs_in_isolated_process_and_is_deterministic() -> None:
    rng = np.random.RandomState(0)
    data = []
    for q in ("a", "b", "c"):
        x = rng.rand(30, 4)
        y = (x[:, 0] > 0.6).astype(np.int64)
        data.append((q, x, y))
    first = lambdamart_leave_one_query_out(data)
    assert set(first) == {"a", "b", "c"} and all(len(v) == 30 for v in first.values())
    assert first == lambdamart_leave_one_query_out(data)
