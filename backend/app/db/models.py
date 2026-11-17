"""Import every model so `Base.metadata` is complete (used by Alembic autogenerate and tests)."""

from app.db.base import Base
from app.domains.auth.models import RefreshToken, User
from app.domains.candidates.models import CandidateProfile, CandidateSkill
from app.domains.ingestion.models import IngestionError, IngestionRun
from app.domains.jobs.models import Job, JobSkill
from app.domains.resumes.models import Resume
from app.domains.search.models import CandidateEmbedding, JobEmbedding
from app.domains.skills.models import Skill, SkillAlias

__all__ = [
    "Base",
    "CandidateEmbedding",
    "CandidateProfile",
    "CandidateSkill",
    "IngestionError",
    "IngestionRun",
    "Job",
    "JobEmbedding",
    "JobSkill",
    "RefreshToken",
    "Resume",
    "Skill",
    "SkillAlias",
    "User",
]
