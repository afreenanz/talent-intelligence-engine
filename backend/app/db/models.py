"""Import every model so `Base.metadata` is complete (used by Alembic autogenerate and tests)."""

from app.db.base import Base
from app.domains.agent.models import Conversation, Message
from app.domains.auth.models import RefreshToken, User
from app.domains.candidates.models import CandidateProfile, CandidateSkill
from app.domains.evaluation.models import EvaluationRun
from app.domains.ingestion.models import IngestionError, IngestionRun
from app.domains.interactions.models import Application, JobInteraction, SavedJob, SearchLog
from app.domains.jobs.models import Job, JobSkill
from app.domains.preferences.models import AgentMemory
from app.domains.resumes.models import Resume
from app.domains.search.models import CandidateEmbedding, JobEmbedding
from app.domains.skills.models import Skill, SkillAlias

__all__ = [
    "AgentMemory",
    "Application",
    "Base",
    "CandidateEmbedding",
    "CandidateProfile",
    "CandidateSkill",
    "Conversation",
    "EvaluationRun",
    "IngestionError",
    "IngestionRun",
    "Job",
    "JobEmbedding",
    "JobInteraction",
    "JobSkill",
    "Message",
    "RefreshToken",
    "Resume",
    "SavedJob",
    "SearchLog",
    "Skill",
    "SkillAlias",
    "User",
]
