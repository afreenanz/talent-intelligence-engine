from sqlalchemy import ForeignKey, Identity, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Skill(Base):
    """Canonical skill vocabulary. `normalized_name` is the identity used for matching."""

    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)  # display form, e.g. "PostgreSQL"
    normalized_name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    category: Mapped[str | None] = mapped_column(Text)


class SkillAlias(Base):
    """Maps alternative spellings to a canonical skill: 'postgres' -> PostgreSQL."""

    __tablename__ = "skill_aliases"

    alias: Mapped[str] = mapped_column(Text, primary_key=True)  # stored normalized
    skill_id: Mapped[int] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True
    )
