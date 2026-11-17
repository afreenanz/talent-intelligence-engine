import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.domains.ingestion.parsers import UnsupportedFileError, read_records
from app.domains.ingestion.schemas import JobRecordIn
from app.domains.skills.extraction import SkillMatcher, _compile


def _matcher(terms: dict[str, int]) -> SkillMatcher:
    return SkillMatcher(tuple((_compile(t), sid) for t, sid in terms.items()))


TERMS = {"python": 1, "c++": 2, "c#": 3, ".net": 4, "node.js": 5, "react": 6, "java": 7, "sql": 8}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Strong Python and SQL skills.", {1, 8}),
        ("Experience with C++ or C#.", {2, 3}),
        ("We use .NET.", {4}),
        ("Node.js services", {5}),
        ("react.js frontend", set()),  # 'react' must not match inside 'react.js'
        ("JavaScript developer", set()),  # 'java' must not match inside 'javascript'
        ("Pythonic code style", set()),
        ("mysql and postgresql", set()),  # 'sql' must not match inside other words
    ],
)
def test_skill_matcher_respects_token_boundaries(text: str, expected: set[int]) -> None:
    assert _matcher(TERMS).find(text) == expected


def test_job_record_splits_csv_skill_lists_and_blank_cells() -> None:
    rec = JobRecordIn.model_validate(
        {
            "external_id": "x1",
            "title": "Backend Engineer",
            "company": "Acme",
            "description": "A description that is long enough to pass validation.",
            "required_skills": "Python; FastAPI | SQL",
            "preferred_skills": "",
            "salary_min": "",
            "employment_type": "Full-time",
            "posted_at": "2026-11-01T10:00:00",
        }
    )
    assert rec.required_skills == ["Python", "FastAPI", "SQL"]
    assert rec.preferred_skills == []
    assert rec.salary_min is None
    assert rec.employment_type is not None and rec.employment_type.value == "full_time"
    assert rec.posted_at is not None and rec.posted_at.tzinfo is not None  # naive -> UTC


@pytest.mark.parametrize(
    "overrides",
    [
        {"description": "too short"},
        {"salary_min": 10, "salary_max": 5, "salary_currency": "INR"},
        {"salary_min": 10},  # salary without currency
        {"experience_min": 5, "experience_max": 2},
        {"posted_at": "2026-11-10", "expires_at": "2026-11-01"},
        {"employment_type": "gig"},
        {"external_id": ""},
    ],
)
def test_job_record_rejects_invalid_records(overrides: dict[str, object]) -> None:
    base = {
        "external_id": "x1",
        "title": "Backend Engineer",
        "company": "Acme",
        "description": "A description that is long enough to pass validation.",
    }
    with pytest.raises(ValidationError):
        JobRecordIn.model_validate({**base, **overrides})


def test_read_records_csv_jsonl_and_json(tmp_path: Path) -> None:
    csv_file = tmp_path / "jobs.csv"
    csv_file.write_text("﻿external_id,title\n1,A\n2,B\n", encoding="utf-8")  # with BOM
    assert [r["external_id"] for r in read_records(csv_file)] == ["1", "2"]

    jsonl = tmp_path / "jobs.jsonl"
    jsonl.write_text('{"external_id": "1"}\n\nnot json\n[1]\n', encoding="utf-8")
    rows = list(read_records(jsonl))
    assert rows[0] == {"external_id": "1"}
    assert "__parse_error__" in rows[1] and "line 3" in rows[1]["__parse_error__"]
    assert "__parse_error__" in rows[2]

    js = tmp_path / "jobs.json"
    js.write_text(json.dumps({"jobs": [{"external_id": "1"}]}), encoding="utf-8")
    assert list(read_records(js)) == [{"external_id": "1"}]


def test_read_records_rejects_unknown_extension(tmp_path: Path) -> None:
    with pytest.raises(UnsupportedFileError):
        list(read_records(tmp_path / "jobs.xlsx"))
