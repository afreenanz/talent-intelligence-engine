import uuid
from datetime import datetime
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from app.db.enums import EmploymentType, LocationType, SkillSource
from app.domains.skills.normalization import MAX_SKILL_LENGTH, normalize_skill_name


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EducationItem(_Strict):
    institution: str = Field(min_length=1, max_length=200)
    degree: str | None = Field(default=None, max_length=200)
    field_of_study: str | None = Field(default=None, max_length=200)
    start_year: int | None = Field(default=None, ge=1950, le=2100)
    end_year: int | None = Field(default=None, ge=1950, le=2100)

    @model_validator(mode="after")
    def _years_ordered(self) -> Self:
        if self.start_year and self.end_year and self.end_year < self.start_year:
            raise ValueError("end_year must be >= start_year")
        return self


class ProjectItem(_Strict):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    technologies: list[str] = Field(default_factory=list, max_length=30)
    url: HttpUrl | None = None


class SkillIn(_Strict):
    name: str = Field(min_length=1, max_length=MAX_SKILL_LENGTH)
    proficiency: int | None = Field(default=None, ge=1, le=5)
    experience_months: int | None = Field(default=None, ge=0, le=720)


class ProfileUpdate(_Strict):
    """PUT semantics: the full editable profile. Omitted optional fields are set to null."""

    full_name: str | None = Field(default=None, max_length=200)
    experience_years: Decimal | None = Field(default=None, ge=0, le=60, decimal_places=1)
    education: list[EducationItem] = Field(default_factory=list, max_length=20)
    projects: list[ProjectItem] = Field(default_factory=list, max_length=50)
    location: str | None = Field(default=None, max_length=200)
    preferred_salary_min: int | None = Field(default=None, ge=0, le=10**10)
    preferred_salary_max: int | None = Field(default=None, ge=0, le=10**10)
    salary_currency: str = Field(default="INR", pattern=r"^[A-Z]{3}$")
    preferred_job_type: EmploymentType | None = None
    preferred_location_type: LocationType | None = None
    profile_summary: str | None = Field(default=None, max_length=5000)
    skills: list[SkillIn] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def _cross_field_checks(self) -> Self:
        lo, hi = self.preferred_salary_min, self.preferred_salary_max
        if lo is not None and hi is not None and lo > hi:
            raise ValueError("preferred_salary_min must be <= preferred_salary_max")
        seen: set[str] = set()
        for s in self.skills:
            norm = normalize_skill_name(s.name)
            if not norm:
                raise ValueError("skill names must not be blank")
            if norm in seen:
                raise ValueError(f"duplicate skill: {s.name!r}")
            seen.add(norm)
        return self


class CandidateSkillOut(BaseModel):
    skill_id: int
    name: str
    normalized_name: str
    proficiency: int | None
    experience_months: int | None
    source: SkillSource


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str | None
    experience_years: float | None  # stored as NUMERIC(4,1); exposed as a JSON number
    education: list[EducationItem]
    projects: list[ProjectItem]
    location: str | None
    preferred_salary_min: int | None
    preferred_salary_max: int | None
    salary_currency: str
    preferred_job_type: EmploymentType | None
    preferred_location_type: LocationType | None
    profile_summary: str | None
    skills: list[CandidateSkillOut]
    created_at: datetime
    updated_at: datetime
