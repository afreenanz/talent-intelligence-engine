"""Public, aggregate-only platform counts for the landing page. Contains no personal data."""

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.deps import DbSession
from app.db.enums import JobStatus
from app.domains.jobs.models import Job
from app.domains.skills.models import Skill

router = APIRouter(tags=["stats"])


class PublicStats(BaseModel):
    active_jobs: int
    companies_hiring: int
    skills_tracked: int


@router.get("/stats", response_model=PublicStats)
def stats(session: DbSession) -> PublicStats:
    active = select(Job).where(Job.status == JobStatus.ACTIVE).subquery()
    return PublicStats(
        active_jobs=session.scalar(select(func.count()).select_from(active)) or 0,
        companies_hiring=session.scalar(select(func.count(func.distinct(active.c.company)))) or 0,
        skills_tracked=session.scalar(
            select(func.count()).select_from(Skill).where(Skill.category.is_not(None))
        )
        or 0,
    )
