"""Dictionary-based skill detection in free text (job descriptions; resumes in 2B).

Deterministic and explainable: a skill is "found" only if its canonical name or a safe alias
appears as a whole token sequence. Limitations (documented, tested):
- Ambiguous skills (Go, R, C, Swift...) are never matched in text, only taken from explicit lists.
- Short or common-word aliases ("rest", "node", "ml", "ts") are not used for text matching.
- No negation handling: "no Java required" still matches Java.
"""

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.skills.models import Skill, SkillAlias

# Aliases that are ordinary English words or too short to match safely in prose.
_UNSAFE_TEXT_ALIASES = {
    "rest",
    "node",
    "spring",
    "express",
    "shell",
    "monitoring",
    "experimentation",
    "transformers",
    "torch",
    "rails",
    "mongo",
    "vue",
    "spark",
    "elt",
}
_MIN_ALIAS_LEN = 4

# Token boundaries. Left: not preceded by a letter/digit or by + # . (part of names such as
# "c++" or ".net"). Right: not followed by a letter/digit/+/#, nor by "." plus a letter/digit,
# so "react" doesn't match inside "react.js", but "...we use .NET." still matches ".net".
_LEFT = r"(?<![a-z0-9+#.])"
_RIGHT = r"(?![a-z0-9+#]|\.[a-z0-9])"


@dataclass(frozen=True)
class SkillMatcher:
    patterns: tuple[tuple[re.Pattern[str], int], ...]

    def find(self, text: str) -> set[int]:
        lowered = text.lower()
        return {skill_id for pattern, skill_id in self.patterns if pattern.search(lowered)}


def _compile(term: str) -> re.Pattern[str]:
    return re.compile(_LEFT + re.escape(term) + _RIGHT)


def build_matcher(session: Session) -> SkillMatcher:
    """Load curated (category NOT NULL), non-ambiguous skills and safe aliases."""
    terms: dict[str, int] = {}
    for skill in session.scalars(
        select(Skill).where(Skill.category.is_not(None), Skill.is_ambiguous.is_(False))
    ):
        terms[skill.normalized_name] = skill.id
    alias_rows = session.execute(
        select(SkillAlias.alias, SkillAlias.skill_id)
        .join(Skill)
        .where(Skill.category.is_not(None), Skill.is_ambiguous.is_(False))
    ).all()
    for alias, skill_id in alias_rows:
        if len(alias) >= _MIN_ALIAS_LEN and alias not in _UNSAFE_TEXT_ALIASES:
            terms.setdefault(alias, skill_id)
    return SkillMatcher(tuple((_compile(term), sid) for term, sid in sorted(terms.items())))
