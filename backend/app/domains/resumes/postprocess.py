"""Deterministic checks on the LLM's extraction.

This is where "never invent experience" is enforced:

1. Skills are kept only if grounded: the skill (or one of its aliases) appears in the resume
   text. Ungrounded skills are dropped and reported as warnings.
2. The dictionary matcher runs on the same text; its finds are merged and provenance is recorded.
3. Name and location are dropped if they don't appear in the text.
4. Work entries are kept but flagged `grounded=false` if company/title aren't in the text.
5. experience_years is computed from date ranges (overlaps merged), not taken from the LLM.
"""

import re
from collections.abc import Callable
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.domains.candidates.schemas import EducationItem, ProjectItem
from app.domains.resumes.schemas import (
    ExtractedWork,
    ParsedResume,
    ParsedSkill,
    ParsedWork,
    ResumeExtraction,
)
from app.domains.skills.normalization import MAX_SKILL_LENGTH, normalize_skill_name

_NON_ALNUM = re.compile(r"[^a-z0-9+#]+")


def _fold(text: str) -> str:
    """Lowercase and reduce punctuation/whitespace to single spaces, for robust substring checks."""
    return f" {_NON_ALNUM.sub(' ', text.lower()).strip()} "


def appears_in(needle: str | None, folded_haystack: str) -> bool:
    if not needle or not needle.strip():
        return False
    folded = _fold(needle)
    return folded.strip() != "" and folded in folded_haystack


# ---------------------------------------------------------------- experience


_DATE = re.compile(r"^\s*(\d{4})(?:[-/.](\d{1,2}))?\s*$")


def _parse_month(value: str | None) -> date | None:
    if not value:
        return None
    m = _DATE.match(value)
    if not m:
        return None
    year, month = int(m.group(1)), int(m.group(2) or 1)
    if not (1950 <= year <= 2100 and 1 <= month <= 12):
        return None
    return date(year, month, 1)


def compute_experience_years(
    work: list[ExtractedWork], today: date
) -> tuple[Decimal | None, str, list[str]]:
    """Union of employment intervals in months -> years (1 decimal).

    Overlapping jobs are merged so concurrent roles aren't double-counted. Entries without a
    parseable start date are skipped and reported, never estimated.
    """
    warnings: list[str] = []
    intervals: list[tuple[int, int]] = []
    for w in work:
        start = _parse_month(w.start_date)
        end = date(today.year, today.month, 1) if w.is_current else _parse_month(w.end_date)
        label = w.title or w.company or "an entry"
        if start is None:
            warnings.append(f"No usable start date for '{label}'; excluded from experience total.")
            continue
        if end is None:
            warnings.append(f"No usable end date for '{label}'; excluded from experience total.")
            continue
        if end < start or start > today:
            warnings.append(
                f"Dates for '{label}' are inconsistent; excluded from experience total."
            )
            continue
        # +1: Jan-2020 to Jan-2020 counts as one month worked
        intervals.append((start.year * 12 + start.month, end.year * 12 + end.month + 1))

    if not intervals:
        return None, "unknown: no datable work experience", warnings
    intervals.sort()
    merged = [intervals[0]]
    for s, e in intervals[1:]:
        if s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    months = sum(e - s for s, e in merged)
    years = (Decimal(months) / 12).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return years, f"sum of {len(merged)} merged date range(s) = {months} months", warnings


# ---------------------------------------------------------------- main entry point

# skill resolver: list of raw names -> {normalized_name: (skill_id, [canonical + alias terms])}
SkillResolver = Callable[[list[str]], dict[str, tuple[int | None, str, list[str]]]]


def postprocess(
    extraction: ResumeExtraction,
    resume_text: str,
    *,
    resolve_skills: SkillResolver,
    dictionary_skills: dict[int, str],
    today: date,
    prompt_version: str,
    text_truncated: bool = False,
) -> ParsedResume:
    """`dictionary_skills` = {skill_id: canonical name} found by the deterministic matcher."""
    folded = _fold(resume_text)
    warnings: list[str] = []

    # ---- skills
    skills: dict[str, ParsedSkill] = {}
    raw_llm = [s for s in extraction.skills if s and len(s) <= MAX_SKILL_LENGTH]
    resolved = resolve_skills(raw_llm)
    for raw in raw_llm:
        norm = normalize_skill_name(raw)
        skill_id, canonical, terms = resolved.get(norm, (None, raw.strip(), [norm]))
        if any(appears_in(t, folded) for t in {raw, canonical, *terms}):
            key = canonical.lower()
            skills.setdefault(key, ParsedSkill(name=canonical, skill_id=skill_id, provenance="llm"))
        else:
            warnings.append(f"Skill '{raw}' was not found in the resume text and was removed.")
    for skill_id, name in dictionary_skills.items():
        key = name.lower()
        if key in skills:
            skills[key] = skills[key].model_copy(update={"provenance": "both"})
        else:
            skills[key] = ParsedSkill(name=name, skill_id=skill_id, provenance="dictionary")

    # ---- identity fields: drop rather than invent
    full_name = extraction.full_name if appears_in(extraction.full_name, folded) else None
    if extraction.full_name and full_name is None:
        warnings.append("The extracted name was not found in the text and was removed.")
    location = extraction.location if appears_in(extraction.location, folded) else None

    # ---- work experience
    work = [
        ParsedWork(
            **w.model_dump(),
            grounded=appears_in(w.company, folded) and appears_in(w.title, folded),
        )
        for w in extraction.work_experience
        if w.company or w.title
    ]
    for w in work:
        if not w.grounded:
            warnings.append(
                f"Work entry '{w.title} at {w.company}' could not be verified in the text."
            )
    years, method, exp_warnings = compute_experience_years(list(work), today)
    warnings += exp_warnings

    # ---- education / projects: coerce into the profile's validated shapes
    education: list[EducationItem] = []
    for e in extraction.education:
        if not e.institution:
            continue
        try:
            education.append(
                EducationItem(
                    institution=e.institution[:200],
                    degree=(e.degree or None) and e.degree[:200],
                    field_of_study=(e.field_of_study or None) and e.field_of_study[:200],
                    start_year=e.start_year,
                    end_year=e.end_year,
                )
            )
        except ValueError:
            warnings.append(f"Education entry '{e.institution}' had invalid years and was removed.")
    projects = [
        ProjectItem(
            name=p.name[:200],
            description=(p.description or None) and p.description[:2000],
            technologies=[t[:64] for t in p.technologies][:30],
        )
        for p in extraction.projects
        if p.name
    ]

    return ParsedResume(
        full_name=full_name,
        location=location,
        summary=(extraction.summary or None) and extraction.summary[:5000],
        skills=list(skills.values()),
        work_experience=work,
        education=education,
        projects=projects,
        preferred_roles=[r[:100] for r in extraction.preferred_roles][:10],
        experience_years=years,
        experience_years_method=method,
        warnings=warnings,
        text_truncated=text_truncated,
        prompt_version=prompt_version,
    )
