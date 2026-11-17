import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.db.enums import EmploymentType, JobStatus, LocationType, SkillImportance


class JobSkillOut(BaseModel):
    skill_id: int
    name: str
    importance: SkillImportance


class JobSummary(BaseModel):
    id: uuid.UUID
    title: str
    company: str
    location: str | None
    city: str | None
    location_type: LocationType | None
    employment_type: EmploymentType | None
    salary_min: int | None
    salary_max: int | None
    salary_currency: str | None
    experience_min: float | None
    experience_max: float | None
    status: JobStatus
    listed_at: datetime
    expires_at: datetime | None


class JobDetail(JobSummary):
    description: str
    source: str
    external_id: str
    posted_at: datetime | None
    duplicate_of_job_id: uuid.UUID | None
    skills: list[JobSkillOut]


class JobPage(BaseModel):
    items: list[JobSummary]
    next_cursor: str | None = Field(
        description="Opaque cursor for the next page; null when there are no more results"
    )
