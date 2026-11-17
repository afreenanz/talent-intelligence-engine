"""Import every model so `Base.metadata` is complete (used by Alembic autogenerate and tests)."""

from app.db.base import Base
from app.domains.auth.models import RefreshToken, User
from app.domains.candidates.models import CandidateProfile, CandidateSkill
from app.domains.skills.models import Skill, SkillAlias

__all__ = [
    "Base",
    "CandidateProfile",
    "CandidateSkill",
    "RefreshToken",
    "Skill",
    "SkillAlias",
    "User",
]
