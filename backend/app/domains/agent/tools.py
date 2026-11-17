"""The agent's tools: thin, validated wrappers over the same services the REST API uses.

Safety properties
- `candidate_id` comes from the authenticated request (ToolContext), NEVER from LLM arguments,
  so a prompt can't make the agent act on another user's data.
- Arguments are validated with each tool's Pydantic input model before anything runs.
- Outputs are validated against an output model before the LLM sees them.
- Errors become structured results ({"ok": false, "error_code", "message"}), never exceptions,
  so the model can recover or explain.
- Consequential tools (writes) are flagged; the graph asks the user before running them.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.core.errors import AppError
from app.db.enums import EmploymentType, LocationType, SkillImportance
from app.domains.candidates import service as candidates
from app.domains.interactions import service as activity
from app.domains.jobs.models import Job, JobSkill
from app.domains.personalization.adjust import PersonalizationContext
from app.domains.preferences import service as prefs
from app.domains.preferences.schemas import PreferenceKey
from app.domains.ranking.service import rank_jobs
from app.domains.ranking.weighted import WeightedRanker
from app.domains.search.schemas import JobFilters, RetrievalResult, RetrievedJob
from app.domains.search.service import EmptySearchError, retrieve_jobs
from app.integrations.embeddings.base import Embedder
from app.integrations.llm.base import ToolSpec
from app.integrations.llm.gemini import _provider_schema

MAX_RESULTS = 10


@dataclass
class ToolContext:
    session: Session
    user_id: uuid.UUID
    candidate_id: uuid.UUID
    embedder: Embedder
    ranker: WeightedRanker


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Out(BaseModel):
    pass


# ---------------------------------------------------------------- shared output shapes


class JobHit(_Out):
    job_id: uuid.UUID
    title: str
    company: str
    city: str | None
    location_type: str | None
    salary_min: int | None
    salary_max: int | None
    salary_currency: str | None
    match_score: float | None = None
    reasons: list[str] = Field(default_factory=list)


def _hit(job: Job, score: float | None = None, reasons: list[str] | None = None) -> JobHit:
    return JobHit(
        job_id=job.id,
        title=job.title,
        company=job.company,
        city=job.city,
        location_type=job.location_type.value if job.location_type else None,
        salary_min=job.salary_min,
        salary_max=job.salary_max,
        salary_currency=job.salary_currency,
        match_score=None if score is None else round(score, 3),
        reasons=(reasons or [])[:3],
    )


def _personalization(ctx: ToolContext) -> PersonalizationContext:
    return PersonalizationContext.from_preferences(
        prefs.effective_preferences(ctx.session, ctx.candidate_id)
    )


# ---------------------------------------------------------------- 1. search_jobs


class SearchJobsIn(_In):
    query: str | None = Field(
        default=None,
        max_length=300,
        description="Free-text search. Omit to recommend from the user's profile.",
    )
    city: str | None = Field(default=None, max_length=100)
    location_type: LocationType | None = None
    employment_type: EmploymentType | None = None
    min_salary: int | None = Field(
        default=None, ge=0, description="Annual minimum. 15 LPA = 1500000 (INR)."
    )
    salary_currency: str = Field(default="INR", pattern=r"^[A-Z]{3}$")
    top_k: int = Field(default=5, ge=1, le=MAX_RESULTS)


class SearchJobsOut(_Out):
    results: list[JobHit]
    note: str | None = None


def search_jobs(ctx: ToolContext, args: SearchJobsIn) -> SearchJobsOut:
    filters = JobFilters(
        city=args.city,
        location_type=args.location_type,
        employment_type=args.employment_type,
        min_salary=args.min_salary,
        salary_currency=args.salary_currency,
    )
    personalization = _personalization(ctx)
    try:
        retrieved = retrieve_jobs(
            ctx.session,
            query=args.query,
            candidate_id=ctx.candidate_id,
            filters=filters,
            top_k=100,
            embedder=ctx.embedder,
            extra_lexical_queries=personalization.preference_queries() if not args.query else None,
        )
    except EmptySearchError as exc:
        return SearchJobsOut(results=[], note=exc.message)
    ranked = rank_jobs(
        ctx.session,
        retrieved,
        ranker=ctx.ranker,
        candidate_id=ctx.candidate_id,
        query=args.query,
        embedding_model=ctx.embedder.spec.name,
        top_k=args.top_k,
        personalization=personalization,
    )
    jobs = {
        j.id: j
        for j in ctx.session.scalars(select(Job).where(Job.id.in_([r.job_id for r in ranked.jobs])))
    }
    activity.record_search(
        ctx.session,
        ctx.candidate_id,
        query=args.query,
        filters=filters.model_dump(mode="json", exclude_defaults=True),
        mode="hybrid",
        ranking="features+agent",
        job_ids=[r.job_id for r in ranked.jobs],
        latency_ms=0,
    )
    results = [_hit(jobs[r.job_id], r.score, r.explanation) for r in ranked.jobs]
    return SearchJobsOut(
        results=results, note=None if results else "No active jobs matched. Try fewer filters."
    )


# ---------------------------------------------------------------- 2. get_job_details


class JobIdIn(_In):
    job_id: uuid.UUID


class JobDetailOut(_Out):
    job_id: uuid.UUID
    title: str
    company: str
    location: str | None
    status: str
    employment_type: str | None
    salary_min: int | None
    salary_max: int | None
    salary_currency: str | None
    experience_min: float | None
    experience_max: float | None
    required_skills: list[str]
    preferred_skills: list[str]
    description: str
    posted_at: datetime | None
    expires_at: datetime | None


def _load_job(ctx: ToolContext, job_id: uuid.UUID) -> Job:
    job = ctx.session.scalar(
        select(Job)
        .where(Job.id == job_id)
        .options(selectinload(Job.skills).joinedload(JobSkill.skill))
    )
    if job is None:
        raise ToolError("not_found", "No job with that id exists.")
    return job


def get_job_details(ctx: ToolContext, args: JobIdIn) -> JobDetailOut:
    job = _load_job(ctx, args.job_id)
    by = {i: [js.skill.name for js in job.skills if js.importance is i] for i in SkillImportance}
    return JobDetailOut(
        job_id=job.id,
        title=job.title,
        company=job.company,
        location=job.location,
        status=job.status.value,
        employment_type=job.employment_type.value if job.employment_type else None,
        salary_min=job.salary_min,
        salary_max=job.salary_max,
        salary_currency=job.salary_currency,
        experience_min=float(job.experience_min) if job.experience_min is not None else None,
        experience_max=float(job.experience_max) if job.experience_max is not None else None,
        required_skills=by[SkillImportance.REQUIRED] or by[SkillImportance.MENTIONED],
        preferred_skills=by[SkillImportance.PREFERRED],
        description=job.description[:1500],
        posted_at=job.posted_at,
        expires_at=job.expires_at,
    )


# -------------------------------------------------- 3. rank_jobs, 5. explain_job_match


class RankJobsIn(_In):
    job_ids: list[uuid.UUID] = Field(min_length=1, max_length=20)


class RankJobsOut(_Out):
    ranked: list[JobHit]
    unknown_job_ids: list[uuid.UUID]


def _rank_ids(ctx: ToolContext, ids: list[uuid.UUID]) -> tuple[Any, list[uuid.UUID]]:
    known = set(ctx.session.scalars(select(Job.id).where(Job.id.in_(ids))))
    retrieved = RetrievalResult(
        jobs=[RetrievedJob(job_id=i, fused_score=1.0) for i in dict.fromkeys(ids) if i in known],
        mode="hybrid",
        lexical_query=None,
        used_candidate_vector=False,
    )
    out = rank_jobs(
        ctx.session,
        retrieved,
        ranker=ctx.ranker,
        candidate_id=ctx.candidate_id,
        query=None,
        embedding_model=ctx.embedder.spec.name,
        top_k=len(ids),
        personalization=_personalization(ctx),
    )
    return out, [i for i in ids if i not in known]


def rank_jobs_tool(ctx: ToolContext, args: RankJobsIn) -> RankJobsOut:
    out, unknown = _rank_ids(ctx, args.job_ids)
    jobs = {
        j.id: j
        for j in ctx.session.scalars(select(Job).where(Job.id.in_([r.job_id for r in out.jobs])))
    }
    return RankJobsOut(
        ranked=[_hit(jobs[r.job_id], r.score, r.explanation) for r in out.jobs],
        unknown_job_ids=unknown,
    )


class ExplainOut(_Out):
    job_id: uuid.UUID
    title: str
    company: str
    score: float
    explanation: list[str]
    features: dict[str, float]
    missing_information: list[str]


def explain_job_match(ctx: ToolContext, args: JobIdIn) -> ExplainOut:
    out, unknown = _rank_ids(ctx, [args.job_id])
    if unknown or not out.jobs:
        raise ToolError("not_found", "No job with that id exists.")
    r = out.jobs[0]
    return ExplainOut(
        job_id=r.job_id,
        title=r.title,
        company=r.company,
        score=round(r.score, 3),
        explanation=r.explanation,
        features={k: round(v, 3) for k, v in r.features.items()},
        missing_information=r.missing_features,
    )


# ---------------------------------------------------------------- 4. analyze_candidate_profile


class EmptyIn(_In):
    pass


class ProfileAnalysisOut(_Out):
    full_name: str | None
    experience_years: float | None
    location: str | None
    skills: list[str]
    saved_jobs: int
    applications: int
    preferences: dict[str, Any]
    missing_fields: list[str]


def analyze_candidate_profile(ctx: ToolContext, _: EmptyIn) -> ProfileAnalysisOut:
    p = candidates.get_my_profile(ctx.session, ctx.user_id)
    fields = {
        "full_name": p.full_name,
        "skills": p.skills,
        "experience_years": p.experience_years,
        "location": p.location,
        "preferred_salary_min": p.preferred_salary_min,
        "profile_summary": p.profile_summary,
    }
    saved, _next = activity.list_saved(ctx.session, ctx.candidate_id, 100, None)
    return ProfileAnalysisOut(
        full_name=p.full_name,
        experience_years=float(p.experience_years) if p.experience_years is not None else None,
        location=p.location,
        skills=[cs.skill.name for cs in p.skills],
        saved_jobs=len(saved),
        applications=len(activity.list_applications(ctx.session, ctx.candidate_id)),
        preferences={
            k: r.memory_value
            for k, r in prefs.effective_preferences(ctx.session, ctx.candidate_id).items()
        },
        missing_fields=[k for k, v in fields.items() if not v],
    )


# ---------------------------------------------------------------- 6. save_job (consequential)


class SaveJobOut(_Out):
    job_id: uuid.UUID
    title: str
    saved: bool
    already_saved: bool


def save_job(ctx: ToolContext, args: JobIdIn) -> SaveJobOut:
    job = _load_job(ctx, args.job_id)
    created = activity.save_job(ctx.session, ctx.candidate_id, job.id)
    return SaveJobOut(job_id=job.id, title=job.title, saved=True, already_saved=not created)


# ---------------------------------------------------------------- 7. get_saved_jobs


class LimitIn(_In):
    limit: int = Field(default=10, ge=1, le=20)


class SavedJobsOut(_Out):
    jobs: list[JobHit]


def get_saved_jobs(ctx: ToolContext, args: LimitIn) -> SavedJobsOut:
    rows, _next = activity.list_saved(ctx.session, ctx.candidate_id, args.limit, None)
    return SavedJobsOut(jobs=[_hit(job) for _saved, job in rows])


# ---------------------------------------------------------------- 8/9. preferences


class UpdatePreferenceIn(_In):
    key: PreferenceKey
    value: dict[str, Any] = Field(
        description=(
            "Shape depends on key. role_categories: {prefer: [...], avoid: [...]} using backend, "
            "frontend, fullstack, data, ml, devops, mobile, qa, security, design, product. "
            "locations: {cities: [...]}. location_type: {value: onsite|remote|hybrid}. "
            "min_salary: {amount: int, currency: 'INR'}. employment_type: "
            "{value: full_time|part_time|contract|internship|temporary}. "
            "company_avoid: {companies: [...]}. skills_to_use: {skills: [...]}"
        )
    )


class PreferenceChangeOut(_Out):
    key: str
    value: dict[str, Any]
    previous: dict[str, Any] | None
    created: bool


def update_candidate_preferences(ctx: ToolContext, args: UpdatePreferenceIn) -> PreferenceChangeOut:
    from app.db.enums import MemorySource

    change = prefs.set_explicit(
        ctx.session, ctx.candidate_id, args.key, args.value, MemorySource.AGENT
    )
    return PreferenceChangeOut(**change.model_dump())


class PreferenceItem(_Out):
    key: str
    value: dict[str, Any]
    stated_by_user: bool
    confidence: float


class PreferencesOut(_Out):
    preferences: list[PreferenceItem]


def get_candidate_preferences(ctx: ToolContext, _: EmptyIn) -> PreferencesOut:
    rows = prefs.effective_preferences(ctx.session, ctx.candidate_id)
    return PreferencesOut(
        preferences=[
            PreferenceItem(
                key=k,
                value=r.memory_value,
                stated_by_user=r.memory_type.value == "explicit_preference",
                confidence=r.confidence,
            )
            for k, r in sorted(rows.items())
        ]
    )


# ---------------------------------------------------------------- 10. get_application_status


class ApplicationStatusIn(_In):
    job_id: uuid.UUID | None = Field(default=None, description="Omit to list all applications.")


class ApplicationItem(_Out):
    application_id: uuid.UUID
    job_id: uuid.UUID
    title: str
    company: str
    status: str
    updated_at: datetime


class ApplicationsOut(_Out):
    applications: list[ApplicationItem]


def get_application_status(ctx: ToolContext, args: ApplicationStatusIn) -> ApplicationsOut:
    rows = activity.list_applications(ctx.session, ctx.candidate_id)
    return ApplicationsOut(
        applications=[
            ApplicationItem(
                application_id=a.id,
                job_id=j.id,
                title=j.title,
                company=j.company,
                status=a.application_status.value,
                updated_at=a.updated_at,
            )
            for a, j in rows
            if args.job_id is None or j.id == args.job_id
        ]
    )


# ---------------------------------------------------------------- registry and execution


class ToolError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code, self.message = code, message


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_model: type[_In]
    output_model: type[_Out]
    fn: Callable[[ToolContext, Any], _Out]
    consequential: bool = False

    def spec(self) -> ToolSpec:
        return ToolSpec(self.name, self.description, _provider_schema(self.input_model))


TOOLS: dict[str, Tool] = {
    t.name: t
    for t in [
        Tool(
            "search_jobs",
            "Search active jobs by text and filters, ranked for this user. Omit query "
            "to recommend from the user's profile.",
            SearchJobsIn,
            SearchJobsOut,
            search_jobs,
        ),
        Tool(
            "get_job_details",
            "Full details of one job by job_id.",
            JobIdIn,
            JobDetailOut,
            get_job_details,
        ),
        Tool(
            "rank_jobs",
            "Rank specific jobs (by job_id) for this user.",
            RankJobsIn,
            RankJobsOut,
            rank_jobs_tool,
        ),
        Tool(
            "analyze_candidate_profile",
            "Summarise the user's profile, activity and missing fields.",
            EmptyIn,
            ProfileAnalysisOut,
            analyze_candidate_profile,
        ),
        Tool(
            "explain_job_match",
            "Explain how well one job matches this user, feature by feature.",
            JobIdIn,
            ExplainOut,
            explain_job_match,
        ),
        Tool(
            "save_job",
            "Save a job to the user's saved list.",
            JobIdIn,
            SaveJobOut,
            save_job,
            consequential=True,
        ),
        Tool(
            "get_saved_jobs", "List the user's saved jobs.", LimitIn, SavedJobsOut, get_saved_jobs
        ),
        Tool(
            "update_candidate_preferences",
            "Store one explicit preference (replaces that key).",
            UpdatePreferenceIn,
            PreferenceChangeOut,
            update_candidate_preferences,
            consequential=True,
        ),
        Tool(
            "get_candidate_preferences",
            "List the user's stated and learned preferences.",
            EmptyIn,
            PreferencesOut,
            get_candidate_preferences,
        ),
        Tool(
            "get_application_status",
            "List the user's job applications and their status.",
            ApplicationStatusIn,
            ApplicationsOut,
            get_application_status,
        ),
    ]
}


def validate_arguments(name: str, raw: dict[str, Any]) -> tuple[Tool, BaseModel] | dict[str, Any]:
    tool = TOOLS.get(name)
    if tool is None:
        return {
            "ok": False,
            "error_code": "unknown_tool",
            "message": f"There is no tool named {name!r}.",
        }
    try:
        return tool, tool.input_model.model_validate(raw)
    except ValidationError as exc:
        errs = "; ".join(
            f"{'.'.join(map(str, e['loc'])) or 'arguments'}: {e['msg']}" for e in exc.errors()
        )
        return {"ok": False, "error_code": "invalid_arguments", "message": errs}


def execute(tool: Tool, ctx: ToolContext, args: BaseModel) -> dict[str, Any]:
    """Run a validated call. Always returns a JSON-ready dict, never raises."""
    try:
        out = tool.fn(ctx, args)
        data = tool.output_model.model_validate(out.model_dump()).model_dump(mode="json")
        return {"ok": True, "data": data}
    except ToolError as exc:
        return {"ok": False, "error_code": exc.code, "message": exc.message}
    except AppError as exc:
        ctx.session.rollback()
        return {"ok": False, "error_code": exc.code, "message": exc.message}
    except SQLAlchemyError:
        ctx.session.rollback()
        return {
            "ok": False,
            "error_code": "tool_failed",
            "message": "The tool failed. Try again later.",
        }


def job_ids_in(result: Any) -> set[str]:
    """Every job_id that appears anywhere in a tool result (used by the grounding check)."""
    found: set[str] = set()
    if isinstance(result, dict):
        for k, v in result.items():
            if k == "job_id" and isinstance(v, str):
                found.add(v)
            else:
                found |= job_ids_in(v)
    elif isinstance(result, list):
        for v in result:
            found |= job_ids_in(v)
    return found


def now() -> datetime:
    return datetime.now(UTC)
