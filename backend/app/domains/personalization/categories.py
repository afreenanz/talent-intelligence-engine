"""Deterministic role-category classification for jobs (needed to apply role preferences).

1. Title rules (most reliable signal; ordered so specific patterns win, e.g. "full stack"
   before "stack", "machine learning" before "learning").
2. Fallback: the job's skills. A category needs at least 2 skills from the curated taxonomy
   and must be the most common one.
Returns a set: a "Full Stack Developer" can be backend and frontend at once.
"""

import re
from collections import Counter
from collections.abc import Iterable

from app.domains.preferences.schemas import RoleCategory as R

_TITLE_RULES: list[tuple[re.Pattern[str], set[R]]] = [
    (re.compile(r"\bfull[\s-]?stack\b"), {R.FULLSTACK, R.BACKEND, R.FRONTEND}),
    (
        re.compile(
            r"\b(machine learning|ml|ai|nlp|computer vision|applied scientist|data scientist)\b"
        ),
        {R.ML},
    ),
    (
        re.compile(
            r"\b(data engineer|analytics engineer|etl|big data|data analyst|bi developer)\b"
        ),
        {R.DATA},
    ),
    (re.compile(r"\b(devops|site reliability|sre|cloud engineer|infrastructure)\b"), {R.DEVOPS}),
    (re.compile(r"\b(android|ios|mobile|flutter|react native)\b"), {R.MOBILE}),
    (re.compile(r"\b(qa|quality|sdet|test|tester|testing)\b"), {R.QA}),
    (re.compile(r"\b(security|appsec|penetration)\b"), {R.SECURITY}),
    (re.compile(r"\b(designer|ux|ui/ux)\b"), {R.DESIGN}),
    (re.compile(r"\b(product manager|product owner)\b"), {R.PRODUCT}),
    (re.compile(r"\b(front[\s-]?end|ui engineer|react|angular|vue|web developer)\b"), {R.FRONTEND}),
    (
        re.compile(
            r"\b(back[\s-]?end|server|api|platform|python developer|java developer|golang|node)\b"
        ),
        {R.BACKEND},
    ),
]

_SKILL_CATEGORY_TO_ROLE: dict[str, R] = {
    "backend": R.BACKEND,
    "frontend": R.FRONTEND,
    "data": R.DATA,
    "ml": R.ML,
    "devops": R.DEVOPS,
    "cloud": R.DEVOPS,
    "mobile": R.MOBILE,
    "testing": R.QA,
    "security": R.SECURITY,
    "design": R.DESIGN,
    "product": R.PRODUCT,
}
MIN_SKILLS_FOR_FALLBACK = 2


def job_role_categories(title: str, skill_categories: Iterable[str | None]) -> frozenset[R]:
    t = title.lower()
    for pattern, cats in _TITLE_RULES:
        if pattern.search(t):
            return frozenset(cats)
    counts = Counter(
        _SKILL_CATEGORY_TO_ROLE[c] for c in skill_categories if c in _SKILL_CATEGORY_TO_ROLE
    )
    if not counts:
        return frozenset()
    role, n = counts.most_common(1)[0]
    return frozenset({role}) if n >= MIN_SKILLS_FOR_FALLBACK else frozenset()
