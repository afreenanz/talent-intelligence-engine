import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.domains.candidates import service as candidates
from app.domains.ranking.deps import RankerDep, RerankerProviderDep
from app.domains.ranking.service import rank_jobs
from app.domains.search import service
from app.domains.search.deps import EmbedderDep
from app.domains.search.schemas import JobFilters, SearchHit, SearchRequest, SearchResponse
from app.integrations.embeddings.base import Embedder

router = APIRouter(tags=["search"])
RANK_DEPTH = 100  # how many retrieved jobs the ranker sees before cutting to top_k


def _search(
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
) -> SearchResponse:
    retrieved = service.retrieve_jobs(
        session,
        query=query,
        candidate_id=candidate_id,
        filters=filters,
        top_k=top_k if ranking == "none" else RANK_DEPTH,
        embedder=embedder,
        mode=mode,
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
    )
