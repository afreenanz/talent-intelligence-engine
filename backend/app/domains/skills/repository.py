from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.domains.skills.models import Skill, SkillAlias
from app.domains.skills.normalization import normalize_skill_name


def resolve_or_create_skills(session: Session, raw_names: Iterable[str]) -> dict[str, Skill]:
    """Map each raw skill name to a canonical Skill, creating unknown ones.

    Returns {normalized_name: Skill}. Resolution order: alias table, then normalized_name.
    Runs a fixed number of queries regardless of how many skills are passed (no N+1).
    Unknown skills are created with category=None; a curated taxonomy is seeded in Milestone 2.
    """
    display_by_norm: dict[str, str] = {}
    for raw in raw_names:
        norm = normalize_skill_name(raw)
        if norm:
            display_by_norm.setdefault(norm, raw.strip())
    if not display_by_norm:
        return {}

    norms = list(display_by_norm)
    resolved: dict[str, Skill] = {}

    alias_rows = session.execute(
        select(SkillAlias.alias, Skill).join(Skill).where(SkillAlias.alias.in_(norms))
    ).all()
    for alias, skill in alias_rows:
        resolved[alias] = skill

    remaining = [n for n in norms if n not in resolved]
    if remaining:
        # INSERT ... ON CONFLICT DO NOTHING is safe under concurrent requests creating the
        # same new skill; the follow-up SELECT then returns whichever row won.
        session.execute(
            insert(Skill)
            .values([{"name": display_by_norm[n], "normalized_name": n} for n in remaining])
            .on_conflict_do_nothing(index_elements=[Skill.normalized_name])
        )
        for skill in session.scalars(select(Skill).where(Skill.normalized_name.in_(remaining))):
            resolved[skill.normalized_name] = skill

    return resolved
