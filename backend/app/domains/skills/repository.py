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


def lookup_skills(
    session: Session, raw_names: Iterable[str]
) -> dict[str, tuple[int | None, str, list[str]]]:
    """Read-only resolution (creates nothing): {normalized: (skill_id, canonical, match terms)}.

    Match terms = canonical normalized name + every alias, used to check whether a skill is
    actually present in a piece of text.
    """
    norms = {normalize_skill_name(n) for n in raw_names} - {""}
    if not norms:
        return {}
    by_alias = dict(
        session.execute(
            select(SkillAlias.alias, SkillAlias.skill_id).where(SkillAlias.alias.in_(norms))
        ).all()
    )
    direct = {
        s.normalized_name: s
        for s in session.scalars(select(Skill).where(Skill.normalized_name.in_(norms)))
    }
    ids = {*by_alias.values(), *(s.id for s in direct.values())}
    skills = {s.id: s for s in session.scalars(select(Skill).where(Skill.id.in_(ids)))}
    aliases: dict[int, list[str]] = {}
    for alias, skill_id in session.execute(
        select(SkillAlias.alias, SkillAlias.skill_id).where(SkillAlias.skill_id.in_(ids))
    ).all():
        aliases.setdefault(skill_id, []).append(alias)

    out: dict[str, tuple[int | None, str, list[str]]] = {}
    for norm in norms:
        skill = direct.get(norm) or skills.get(by_alias.get(norm, -1))
        if skill is not None:
            out[norm] = (skill.id, skill.name, [skill.normalized_name, *aliases.get(skill.id, [])])
    return out
