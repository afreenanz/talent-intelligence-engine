from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.domains.candidates import service as candidates
from app.domains.search import service
from app.domains.search.deps import EmbedderDep
from app.domains.search.schemas import SearchHit, SearchRequest, SearchResponse

router = APIRouter(prefix="/jobs", tags=["search"])


@router.post("/search", response_model=SearchResponse)
def search_jobs(
    body: SearchRequest, user: CurrentUser, session: DbSession, embedder: EmbedderDep
) -> SearchResponse:
    """Lexical, dense or hybrid search. With no query and `use_profile=true`, the candidate's own
    profile is the query (recommendation mode). Ranking and personalisation come in Milestones 4-5;
    this endpoint returns *retrieval* scores only."""
    candidate_id = candidates.get_my_profile(session, user.id).id if body.use_profile else None
    result = service.retrieve_jobs(
        session,
        query=body.query,
        candidate_id=candidate_id,
        filters=body.filters,
        top_k=body.top_k,
        embedder=embedder,
        mode=body.mode,
    )
    return SearchResponse(
        results=[
            SearchHit(**{k: getattr(j, k) for k in SearchHit.model_fields}) for j in result.jobs
        ],
        mode=result.mode,
        lexical_query=result.lexical_query,
        used_profile=result.used_candidate_vector,
        timings_ms=result.timings_ms,
    )
