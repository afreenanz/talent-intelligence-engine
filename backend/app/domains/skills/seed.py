"""Load the curated skill taxonomy (data/taxonomy/*.json) into `skills` and `skill_aliases`.

Idempotent: running it twice changes nothing. A skill previously created ad hoc (for example
from a candidate's free-text input, with category NULL) is adopted by the taxonomy: its
category and display name are filled in, and its id is preserved so existing links stay valid.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.domains.skills.models import Skill, SkillAlias
from app.domains.skills.normalization import normalize_skill_name


class TaxonomySkill(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    category: str
    aliases: list[str] = []
    is_ambiguous: bool = False


class Taxonomy(BaseModel):
    version: str
    skills: list[TaxonomySkill]


@dataclass
class SeedResult:
    skills: int
    aliases: int


def load_taxonomy(path: Path) -> Taxonomy:
    return Taxonomy.model_validate(json.loads(path.read_text(encoding="utf-8")))


def seed_skills(session: Session, taxonomy: Taxonomy) -> SeedResult:
    rows = [
        {
            "name": s.name,
            "normalized_name": normalize_skill_name(s.name),
            "category": s.category,
            "is_ambiguous": s.is_ambiguous,
        }
        for s in taxonomy.skills
    ]
    stmt = insert(Skill).values(rows)
    session.execute(
        stmt.on_conflict_do_update(
            index_elements=[Skill.normalized_name],
            set_={
                "name": stmt.excluded.name,
                "category": stmt.excluded.category,
                "is_ambiguous": stmt.excluded.is_ambiguous,
            },
        )
    )
    # .all() matters: a Result object has a .keys() method, so dict(result) would treat it as
    # a mapping instead of an iterable of (name, id) pairs.
    ids: dict[str, int] = dict(
        session.execute(
            select(Skill.normalized_name, Skill.id).where(
                Skill.normalized_name.in_([r["normalized_name"] for r in rows])
            )
        ).all()
    )

    alias_rows = [
        {"alias": normalize_skill_name(alias), "skill_id": ids[normalize_skill_name(s.name)]}
        for s in taxonomy.skills
        for alias in s.aliases
    ]
    if alias_rows:
        a_stmt = insert(SkillAlias).values(alias_rows)
        session.execute(
            a_stmt.on_conflict_do_update(
                index_elements=[SkillAlias.alias], set_={"skill_id": a_stmt.excluded.skill_id}
            )
        )
    session.commit()
    return SeedResult(skills=len(rows), aliases=len(alias_rows))
