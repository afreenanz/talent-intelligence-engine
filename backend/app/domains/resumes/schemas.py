"""Three shapes, deliberately separate:

1. `ResumeExtraction`: what the LLM must return (kept simple; provider-side schema support
   is a subset of JSON Schema, and length limits aren't enforced there).
2. `ParsedResume`: what we store after deterministic post-processing (grounding, computed
   experience, warnings). This is what the user reviews.
3. `ResumeApplyRequest`: what the user confirms, possibly edited, to update their profile.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.db.enums import ResumeStatus
from app.domains.candidates.schemas import EducationItem, ProjectItem, SkillIn

# ---------------------------------------------------------------- 1. LLM output contract


class ExtractedWork(BaseModel):
    company: str | None = Field(description="Employer name exactly as written in the resume.")
    title: str | None = Field(description="Job title exactly as written.")
    start_date: str | None = Field(description="Start as YYYY-MM or YYYY, or null if not stated.")
    end_date: str | None = Field(
        description="End as YYYY-MM or YYYY; null if not stated or if current."
    )
    is_current: bool = Field(description="True only if the resume says present/current/now.")


class ExtractedEducation(BaseModel):
    institution: str | None
    degree: str | None
    field_of_study: str | None
    start_year: int | None
    end_year: int | None


class ExtractedProject(BaseModel):
    name: str | None
    description: str | None
    technologies: list[str]


class ResumeExtraction(BaseModel):
    full_name: str | None = Field(description="Candidate's name, or null if not present.")
    location: str | None = Field(description="Candidate's city/region if stated, else null.")
    summary: str | None = Field(description="The resume's own summary/objective text, or null.")
    skills: list[str] = Field(description="Technical skills explicitly written in the resume.")
    work_experience: list[ExtractedWork]
    education: list[ExtractedEducation]
    projects: list[ExtractedProject]
    preferred_roles: list[str] = Field(
        description="Roles the candidate explicitly says they want; empty if not stated."
    )


# ---------------------------------------------------------------- 2. Stored, post-processed


class ParsedSkill(BaseModel):
    name: str
    skill_id: int | None
    provenance: Literal["llm", "dictionary", "both"]


class ParsedWork(ExtractedWork):
    grounded: bool  # company and title both appear in the resume text


class ParsedResume(BaseModel):
    full_name: str | None
    location: str | None
    summary: str | None
    skills: list[ParsedSkill]
    work_experience: list[ParsedWork]
    education: list[EducationItem]
    projects: list[ProjectItem]
    preferred_roles: list[str]
    # Computed by our code from work_experience dates; never taken from the LLM.
    experience_years: float | None  # computed as Decimal, exposed as a JSON number
    experience_years_method: str
    warnings: list[str]
    text_truncated: bool
    prompt_version: str


# ---------------------------------------------------------------- API


class ResumeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    original_filename: str
    size_bytes: int
    page_count: int | None
    parsing_status: ResumeStatus
    parsing_error: str | None
    parsed_data: ParsedResume | None
    llm_model: str | None
    created_at: datetime
    reviewed_at: datetime | None


class ResumeApplyRequest(BaseModel):
    """The reviewed (possibly edited) data. Null scalars mean "leave the profile unchanged"."""

    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    experience_years: Decimal | None = Field(default=None, ge=0, le=60, decimal_places=1)
    profile_summary: str | None = Field(default=None, max_length=5000)
    skills: list[SkillIn] = Field(default_factory=list, max_length=100)
    education: list[EducationItem] | None = Field(default=None, max_length=20)
    projects: list[ProjectItem] | None = Field(default=None, max_length=50)
