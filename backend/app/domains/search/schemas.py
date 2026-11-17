import uuid
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.db.enums import EmploymentType, LocationType

RetrievalMode = Literal["lexical", "dense", "hybrid"]


class JobFilters(BaseModel):
    """Hard filters, applied in SQL *before* ranking in every retriever.

    Unknown values are kept, not excluded: a job that doesn't state a salary isn't removed by a
    salary filter, because most real postings omit it. Only jobs *known* to fail are filtered.
    """

    model_config = ConfigDict(extra="forbid")

    city: str | None = Field(default=None, max_length=100)
    location_type: LocationType | None = None
    employment_type: EmploymentType | None = None
    min_salary: int | None = Field(default=None, ge=0, description="annual, in salary_currency")
    salary_currency: str = Field(default="INR", pattern=r"^[A-Z]{3}$")
    max_experience_required: float | None = Field(
        default=None, ge=0, le=60, description="exclude jobs whose minimum experience is higher"
    )
    company: str | None = Field(default=None, max_length=100)


@dataclass(frozen=True)
class RetrievalParams:
    depth: int = 100  # candidates fetched from each retriever before fusion
    rrf_k: int = 60
    lexical_weight: float = 1.0
    dense_weight: float = 1.0


@dataclass
class RetrievedJob:
    job_id: uuid.UUID
    lexical_rank: int | None = None
    semantic_rank: int | None = None
    lexical_score: float | None = None
    similarity: float | None = None
    fused_score: float = 0.0
    title: str = ""
    company: str = ""


@dataclass
class RetrievalResult:
    jobs: list[RetrievedJob]
    mode: RetrievalMode
    lexical_query: str | None
    used_candidate_vector: bool
    timings_ms: dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------- API


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str | None = Field(default=None, max_length=500)
    filters: JobFilters = Field(default_factory=JobFilters)
    top_k: int = Field(default=20, ge=1, le=100)
    mode: RetrievalMode = "hybrid"
    use_profile: bool = Field(
        default=False,
        description="With no query: search with the candidate's profile (recommendation mode)",
    )


class SearchHit(BaseModel):
    job_id: uuid.UUID
    title: str
    company: str
    lexical_rank: int | None
    semantic_rank: int | None
    lexical_score: float | None
    similarity: float | None
    fused_score: float


class SearchResponse(BaseModel):
    results: list[SearchHit]
    mode: RetrievalMode
    lexical_query: str | None
    used_profile: bool
    timings_ms: dict[str, float]
