"""retrieve_jobs: the single entry point used by the API, the ranking engine and the agent."""

import time
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import AppError
from app.domains.candidates.models import CandidateProfile, CandidateSkill
from app.domains.jobs.models import Job
from app.domains.search import retrievers
from app.domains.search.fusion import reciprocal_rank_fusion
from app.domains.search.indexing import candidate_vector
from app.domains.search.schemas import (
    JobFilters,
    RetrievalMode,
    RetrievalParams,
    RetrievalResult,
    RetrievedJob,
)
from app.integrations.embeddings.base import Embedder, Vector

MAX_PROFILE_QUERY_SKILLS = 12


class EmptySearchError(AppError):
    code = "empty_search"


def retrieve_jobs(
    session: Session,
    *,
    query: str | None,
    candidate_id: uuid.UUID | None,
    filters: JobFilters,
    top_k: int,
    embedder: Embedder,
    mode: RetrievalMode = "hybrid",
    params: RetrievalParams | None = None,
    extra_lexical_queries: list[str] | None = None,
) -> RetrievalResult:
    """Retrieve jobs by query text, or by candidate profile when no query is given."""
    params = params or RetrievalParams()
    timings: dict[str, float] = {}
    query = (query or "").strip() or None

    lexical_query = query
    vector: Vector | None = None
    used_candidate = False
    if query is None:
        if candidate_id is None:
            raise EmptySearchError("Provide a query, or search with your profile")
        profile = _load_profile(session, candidate_id)
        lexical_query = _profile_lexical_query(profile)
        t = time.perf_counter()
        vector = candidate_vector(session, profile, embedder)
        timings["candidate_vector"] = _ms(t)
        used_candidate = vector is not None
        if vector is None and not lexical_query:
            raise EmptySearchError("Your profile is empty: add skills or a summary first")

    lexical: list[tuple[uuid.UUID, float]] = []
    dense: list[tuple[uuid.UUID, float]] = []
    if mode in ("lexical", "hybrid") and lexical_query:
        t = time.perf_counter()
        lexical = retrievers.lexical_search(session, lexical_query, filters, params.depth)
        timings["lexical"] = _ms(t)
    if mode in ("dense", "hybrid"):
        if vector is None and query is not None:
            t = time.perf_counter()
            vector = embedder.encode_queries([query])[0]
            timings["query_embedding"] = _ms(t)
        if vector is not None:
            t = time.perf_counter()
            dense = retrievers.dense_search(
                session, vector, embedder.spec.name, filters, params.depth
            )
            timings["dense"] = _ms(t)

    # Extra lexical channels (e.g. the candidate's preferred role categories). Each is fused as
    # its own RRF list, so it widens the candidate pool without diluting the main query.
    extra: dict[str, list[uuid.UUID]] = {}
    if mode == "hybrid":
        for i, q in enumerate(extra_lexical_queries or []):
            t = time.perf_counter()
            extra[f"pref{i}"] = [
                j for j, _ in retrievers.lexical_search(session, q, filters, params.depth)
            ]
            timings[f"preference_channel_{i}"] = _ms(t)

    t = time.perf_counter()
    lex_rank = {jid: (r, s) for r, (jid, s) in enumerate(lexical, start=1)}
    den_rank = {jid: (r, s) for r, (jid, s) in enumerate(dense, start=1)}
    if mode == "lexical":
        ordered = [(jid, s) for jid, s in lexical]
    elif mode == "dense":
        ordered = [(jid, s) for jid, s in dense]
    else:
        ordered = reciprocal_rank_fusion(
            {"lexical": [j for j, _ in lexical], "dense": [j for j, _ in dense], **extra},
            k=params.rrf_k,
            weights={"lexical": params.lexical_weight, "dense": params.dense_weight},
        )
    ordered = ordered[:top_k]

    results = [
        RetrievedJob(
            job_id=jid,
            lexical_rank=lex_rank.get(jid, (None, None))[0],
            semantic_rank=den_rank.get(jid, (None, None))[0],
            lexical_score=lex_rank.get(jid, (None, None))[1],
            similarity=den_rank.get(jid, (None, None))[1],
            fused_score=score,
        )
        for jid, score in ordered
    ]
    _attach_titles(session, results)
    timings["fusion_and_load"] = _ms(t)
    return RetrievalResult(results, mode, lexical_query, used_candidate, timings, vector)


def _load_profile(session: Session, candidate_id: uuid.UUID) -> CandidateProfile:
    profile = session.scalar(
        select(CandidateProfile)
        .where(CandidateProfile.id == candidate_id)
        .options(selectinload(CandidateProfile.skills).joinedload(CandidateSkill.skill))
    )
    if profile is None:
        raise EmptySearchError("Candidate profile not found")
    return profile


def _profile_lexical_query(profile: CandidateProfile) -> str | None:
    # Highest-proficiency skills first; unknown proficiency last.
    ranked = sorted(profile.skills, key=lambda cs: -(cs.proficiency or 0))
    names = [cs.skill.name for cs in ranked[:MAX_PROFILE_QUERY_SKILLS]]
    return " ".join(names) or None


def _attach_titles(session: Session, results: list[RetrievedJob]) -> None:
    if not results:
        return
    rows = session.execute(
        select(Job.id, Job.title, Job.company).where(Job.id.in_([r.job_id for r in results]))
    ).all()
    by_id = {row.id: row for row in rows}
    for r in results:
        r.title, r.company = by_id[r.job_id].title, by_id[r.job_id].company


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)
