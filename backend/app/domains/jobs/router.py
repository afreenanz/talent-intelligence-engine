import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.core.errors import AppError, NotFoundError
from app.db.enums import EmploymentType, JobStatus, LocationType
from app.domains.jobs import repository
from app.domains.jobs.models import Job
from app.domains.jobs.schemas import JobDetail, JobPage, JobSkillOut, JobSummary

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _summary(job: Job) -> JobSummary:
    return JobSummary.model_validate(
        {k: getattr(job, k) for k in JobSummary.model_fields}, from_attributes=False
    )


@router.get("", response_model=JobPage)
def list_jobs(
    _: CurrentUser,
    session: DbSession,
    status: JobStatus = JobStatus.ACTIVE,
    city: Annotated[str | None, Query(max_length=100)] = None,
    location_type: LocationType | None = None,
    employment_type: EmploymentType | None = None,
    company: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
) -> JobPage:
    filters = repository.JobListFilters(status, city, location_type, employment_type, company)
    try:
        jobs, next_cursor = repository.list_jobs(session, filters, limit, cursor)
    except repository.InvalidCursorError as exc:
        raise AppError("Invalid pagination cursor") from exc
    return JobPage(items=[_summary(j) for j in jobs], next_cursor=next_cursor)


@router.get("/{job_id}", response_model=JobDetail)
def get_job(job_id: uuid.UUID, _: CurrentUser, session: DbSession) -> JobDetail:
    job = repository.get_job_with_skills(session, job_id)
    if job is None:
        raise NotFoundError("Job not found")
    base = {k: getattr(job, k) for k in JobDetail.model_fields if k != "skills"}
    skills = [
        JobSkillOut(skill_id=js.skill_id, name=js.skill.name, importance=js.importance)
        for js in job.skills
    ]
    return JobDetail.model_validate({**base, "skills": skills})
