"""TalentCLEF 2026 Task A adapter: load, and deterministically parse jobs (queries) and CVs.

Direction: a job description is the query; CVs are the documents (job -> candidates).
The ranking features are symmetric in (candidate, job), so the same feature code is evaluated.

Parsing is deterministic (no LLM): no data leaves the machine, and runs are reproducible.

Skills: our curated taxonomy is tech-focused (138 skills), while TalentCLEF covers cashiers,
paralegals, HVAC engineers and more. So each job's own "Required Skills" list is its
vocabulary, and a CV "has" a skill if that term appears in it (same token-boundary matching
as production). This measures the *ranking logic*, not taxonomy coverage.
"""

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from app.domains.resumes.postprocess import compute_experience_years
from app.domains.resumes.schemas import ExtractedWork

# Fixed reference date for "Present" so runs are reproducible (dataset released 2026).
REFERENCE_DATE = date(2026, 4, 1)

_SKILL_HEADING = re.compile(r"^\s*(about\s+)?required\s+skills\s*:?\s*$", re.I)
_EXP_HEADING = re.compile(r"^\s*(professional|work)\s+experience\s*:?\s*$", re.I)
_MONTHS = {
    m: i
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1
    )
}
_DATE = r"(?:([A-Za-z]{3,9})\.?\s+)?(\d{4})"
_DASH = r"\s*(?:-|\u2013|\u2014|to)\s*"  # hyphen, en dash, em dash, "to"
_RANGE = re.compile(_DATE + _DASH + r"(?:" + _DATE + r"|(present|current|now))", re.I)
_YEARS_REQ = re.compile(r"(\d{1,2})\s*\+?\s*(?:-\s*\d{1,2}\s*)?years?", re.I)


@dataclass(frozen=True)
class TCJob:
    query_id: str
    text: str
    required_skills: tuple[str, ...]
    experience_min: float | None


@dataclass(frozen=True)
class TCResume:
    doc_id: str
    text: str
    experience_years: float | None


@dataclass
class TCDataset:
    jobs: dict[str, TCJob]
    resumes: dict[str, TCResume]
    qrels: dict[str, dict[str, int]]


def parse_required_skills(text: str) -> tuple[str, ...]:
    skills: list[str] = []
    in_section = False
    for line in text.splitlines():
        if _SKILL_HEADING.match(line):
            in_section = True
            continue
        if in_section:
            stripped = line.strip()
            if stripped.startswith(("-", "•", "*")):
                skill = stripped.lstrip("-•* ").strip().rstrip(".")
                if 1 < len(skill) <= 60:
                    skills.append(skill)
            elif skills:  # a non-bullet or blank line *after* bullets ends the section
                break
            # Non-bullet text before the first bullet (an intro sentence) is skipped.
    return tuple(dict.fromkeys(skills))  # de-duplicate, keep order


def parse_experience_requirement(text: str) -> float | None:
    """Smallest "N years" figure mentioned in the job, or None. Deliberately conservative."""
    values = [int(m.group(1)) for m in _YEARS_REQ.finditer(text) if int(m.group(1)) <= 30]
    return float(min(values)) if values else None


def _month(token: str | None) -> int:
    return _MONTHS.get((token or "jan")[:3].lower(), 1)


def experience_section(text: str) -> str:
    """Lines between an experience heading and the next ALL-CAPS heading."""
    out: list[str] = []
    inside = False
    for line in text.splitlines():
        if _EXP_HEADING.match(line.strip()):
            inside = True
            continue
        if inside and line.strip().isupper() and 3 < len(line.strip()) < 40:
            break
        if inside:
            out.append(line)
    return "\n".join(out)


def parse_resume_experience(text: str, today: date = REFERENCE_DATE) -> float | None:
    """Total years from date ranges inside the experience section only (education excluded)."""
    work: list[ExtractedWork] = []
    for m in _RANGE.finditer(experience_section(text)):
        m1, y1, m2, y2, present = m.groups()
        start = f"{y1}-{_month(m1):02d}"
        end = None if present else f"{y2}-{_month(m2):02d}"
        work.append(
            ExtractedWork(
                company="x", title="x", start_date=start, end_date=end, is_current=bool(present)
            )
        )
    years, _, _ = compute_experience_years(work, today)
    return None if years is None else float(years)


def load(root: Path, split: str = "development", lang: str = "en") -> TCDataset:
    base = root / "TaskA" / split / lang
    jobs = {}
    for f in sorted((base / "queries").iterdir()):
        text = f.read_text(encoding="utf-8")
        jobs[f.name] = TCJob(
            f.name, text, parse_required_skills(text), parse_experience_requirement(text)
        )
    resumes = {}
    for f in sorted((base / "corpus").iterdir()):
        text = f.read_text(encoding="utf-8")
        resumes[f.name] = TCResume(f.name, text, parse_resume_experience(text))
    qrels: dict[str, dict[str, int]] = {}
    qfile = base / "qrels.tsv"
    if qfile.exists():
        for line in qfile.read_text().splitlines():
            if line.strip():
                qid, _, doc, rel = line.split()
                if int(rel) > 0:
                    qrels.setdefault(qid, {})[doc] = int(rel)
    return TCDataset(jobs, resumes, qrels)
