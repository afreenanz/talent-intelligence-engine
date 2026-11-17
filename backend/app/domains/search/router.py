import time
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.domains.candidates import service as candidates
from app.domains.interactions.service import record_search
from app.domains.personalization.adjust import PersonalizationContext
from app.domains.preferences.service import effective_preferences
from app.domains.ranking.deps import RankerDep, RerankerProviderDep
from app.domains.ranking.service import rank_jobs
from app.domains.search import service
from app.domains.search.deps import EmbedderDep
from app.domains.search.schemas import JobFilters, SearchHit, SearchRequest, SearchResponse
from app.domains.skills.repository import lookup_skills
from app.integrations.embeddings.base import Embedder

router = APIRouter(tags=["search"])
RANK_DEPTH = 100  # how many retrieved jobs the ranker sees before cutting to top_k


def _search(
    session: DbSession,
    embedder: Embedder,
    ranker: RankerDep,
    reranker_provider: RerankerProviderDep,
    *,
    log_for: uuid.UUID,
    personalize: bool = True,
    explore_slots: int = 0,
    query: str | None,
    candidate_id: uuid.UUID | None,
    filters: JobFilters,
    top_k: int,
    mode: Literal["lexical", "dense", "hybrid"],
    ranking: str,
) -> SearchResponse:
    """Run a search, then log it with one impression per returned job (positions 1..n)."""
    started = time.perf_counter()
    context = _personalization(session, log_for) if personalize and ranking != "none" else None
    response = _run_search(
        session,
        embedder,
        ranker,
        reranker_provider,
        query=query,
        candidate_id=candidate_id,
        filters=filters,
        top_k=top_k,
        mode=mode,
        ranking=ranking,
        personalization=context,
        explore_slots=explore_slots,
    )
    log = record_search(
        session,
        log_for,
        query=query,
        filters=filters.model_dump(mode="json", exclude_defaults=True),
        mode=mode,
        ranking=ranking,
        job_ids=[h.job_id for h in response.results],
        latency_ms=int((time.perf_counter() - started) * 1000),
    )
    response.search_log_id = log.id
    return response


def _run_search(
    session: DbSession,
    embedder: Embedder,
    ranker: RankerDep,
    reranker_provider: RerankerProviderDep,
    *,
    query: str | None,
    candidate_id: uuid.UUID | None,
    filters: JobFilters,
    top_k: int,
    mode: Literal["lexical", "dense", "hybrid"],
    ranking: str,
    personalization: PersonalizationContext | None = None,
    explore_slots: int = 0,
) -> SearchResponse:
    retrieved = service.retrieve_jobs(
        session,
        query=query,
        candidate_id=candidate_id,
        filters=filters,
        top_k=top_k if ranking == "none" else RANK_DEPTH,
        embedder=embedder,
        mode=mode,
        # Recommendation mode only: preferred role categories become extra retrieval channels.
        extra_lexical_queries=(
            personalization.preference_queries() if personalization and query is None else None
        ),
    )
    base = {
        "mode": retrieved.mode,
        "lexical_query": retrieved.lexical_query,
        "used_profile": retrieved.used_candidate_vector,
    }
    if ranking == "none":
        hits = [
            SearchHit(
                **{
                    k: getattr(j, k)
                    for k in (
                        "job_id",
                        "title",
                        "company",
                        "lexical_rank",
                        "semantic_rank",
                        "lexical_score",
                        "similarity",
                        "fused_score",
                    )
                }
            )
            for j in retrieved.jobs
        ]
        return SearchResponse(results=hits, timings_ms=retrieved.timings_ms, **base)

    out = rank_jobs(
        session,
        retrieved,
        ranker=ranker,
        candidate_id=candidate_id,
        query=query,
        embedding_model=embedder.spec.name,
        stage=ranking,  # type: ignore[arg-type]
        reranker=reranker_provider() if ranking == "features+cross_encoder" else None,
        top_k=top_k,
        personalization=personalization,
        explore_slots=explore_slots,
    )
    hits = [
        SearchHit(
            job_id=r.job_id,
            title=r.title,
            company=r.company,
            lexical_rank=r.lexical_rank,
            semantic_rank=r.semantic_rank,
            score=round(r.score, 4),
            stage1_score=round(r.stage1_score, 4),
            cross_encoder_score=None
            if r.cross_encoder_score is None
            else round(r.cross_encoder_score, 3),
            explanation=r.explanation,
            features={k: round(v, 3) for k, v in r.features.items()},
            contributions={k: round(v, 4) for k, v in r.contributions.items()},
            missing_features=r.missing_features,
            personalization=round(r.personalization, 4),
            role_categories=r.role_categories,
            exploration=r.exploration,
        )
        for r in out.jobs
    ]
    return SearchResponse(
        results=hits,
        ranking=ranking,
        weights_version=out.weights_version,
        timings_ms={**retrieved.timings_ms, **out.timings_ms},
        **base,
    )


def _personalization(session: DbSession, candidate_id: uuid.UUID) -> PersonalizationContext:
    effective = effective_preferences(session, candidate_id)
    skills_pref = effective.get("skills_to_use")
    names = list(skills_pref.memory_value.get("skills", [])) if skills_pref else []
    resolved = lookup_skills(session, names) if names else {}
    # {lowercased skill name the user typed: skill_id}, for skills that exist in the vocabulary
    ids = {
        name.lower(): hit[0]
        for name in names
        if (hit := resolved.get(name.lower())) is not None and hit[0] is not None
    }
    return PersonalizationContext.from_preferences(effective, ids)


@router.post("/jobs/search", response_model=SearchResponse)
def search_jobs(
    body: SearchRequest,
    user: CurrentUser,
    session: DbSession,
    embedder: EmbedderDep,
    ranker: RankerDep,
    reranker_provider: RerankerProviderDep,
) -> SearchResponse:
    """Retrieve (lexical / dense / hybrid), then rank. When you search with a query, your profile
    (if filled in) still feeds the ranking features: skills, experience, salary, location."""
    profile = candidates.get_my_profile(session, user.id)
    return _search(
        session,
        embedder,
        ranker,
        reranker_provider,
        query=body.query,
        candidate_id=profile.id if (body.use_profile or body.query) else None,
        filters=body.filters,
        top_k=body.top_k,
        mode=body.mode,
        ranking=body.ranking,
        log_for=profile.id,
        personalize=body.personalize,
    )


@router.get("/recommendations", response_model=SearchResponse, tags=["recommendations"])
def recommendations(
    user: CurrentUser,
    session: DbSession,
    embedder: EmbedderDep,
    ranker: RankerDep,
    reranker_provider: RerankerProviderDep,
    top_k: Annotated[int, Query(ge=1, le=50)] = 20,
    ranking: Annotated[Literal["features", "features+cross_encoder"], Query()] = "features",
    personalize: bool = True,
) -> SearchResponse:
    """Jobs for you, from your profile alone. Personalisation from your activity is Milestone 5."""
    profile = candidates.get_my_profile(session, user.id)
    return _search(
        session,
        embedder,
        ranker,
        reranker_provider,
        query=None,
        candidate_id=profile.id,
        filters=JobFilters(),
        top_k=top_k,
        mode="hybrid",
        ranking=ranking,
        log_for=profile.id,
        personalize=personalize,
        # 2 exploration slots per 20 recommendations (none in short lists)
        explore_slots=2 if personalize and top_k >= 10 else 0,
    )
