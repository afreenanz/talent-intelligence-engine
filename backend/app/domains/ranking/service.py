"""rank_jobs: stage 1 (weighted features), optional stage 2 (cross-encoder on top N), explanations.

Independent of any LLM. Inputs are retrieval results plus database facts, and output order is
fully determined by the features, the weights file and (optionally) the cross-encoder.
"""

import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.enums import SkillImportance
from app.domains.candidates.models import CandidateProfile, CandidateSkill
from app.domains.jobs.models import Job, JobSkill
from app.domains.ranking.cross_encoder import Reranker, sigmoid
from app.domains.ranking.explain import explain
from app.domains.ranking.features import CandidateFacts, FeatureVector, JobFacts, compute_features
from app.domains.ranking.weighted import WeightedRanker
from app.domains.search.indexing import candidate_text, job_text
from app.domains.search.models import JobEmbedding
from app.domains.search.schemas import RetrievalResult

RankingStage = Literal["none", "features", "features+cross_encoder"]
CROSS_ENCODER_TOP_N = 50
CROSS_ENCODER_BLEND = 0.5  # final = (1 - blend)*stage1 + blend*sigmoid(cross-encoder logit)


@dataclass
class RankedJob:
    job_id: uuid.UUID
    title: str
    company: str
    score: float
    stage1_score: float
    cross_encoder_score: float | None
    features: dict[str, float]
    contributions: dict[str, float]
    missing_features: list[str]
    explanation: list[str]
    lexical_rank: int | None
    semantic_rank: int | None


@dataclass
class RankingOutput:
    jobs: list[RankedJob]
    stage: RankingStage
    weights_version: str
    timings_ms: dict[str, float] = field(default_factory=dict)


def candidate_facts(profile: CandidateProfile | None) -> CandidateFacts:
    if profile is None:
        return CandidateFacts()
    return CandidateFacts(
        skill_ids=frozenset(cs.skill_id for cs in profile.skills),
        experience_years=float(profile.experience_years)
        if profile.experience_years is not None
        else None,
        city=_city_of(profile.location),
        preferred_location_type=profile.preferred_location_type,
        min_salary=profile.preferred_salary_min,
        salary_currency=profile.salary_currency,
        preferred_job_type=profile.preferred_job_type,
    )


def _city_of(location: str | None) -> str | None:
    from app.domains.ingestion.normalize import parse_location

    return parse_location(location).city if location else None


def job_facts(job: Job) -> JobFacts:
    by_imp: dict[SkillImportance, set[int]] = {i: set() for i in SkillImportance}
    for js in job.skills:
        by_imp[js.importance].add(js.skill_id)
    return JobFacts(
        required_skill_ids=frozenset(by_imp[SkillImportance.REQUIRED]),
        preferred_skill_ids=frozenset(by_imp[SkillImportance.PREFERRED]),
        mentioned_skill_ids=frozenset(by_imp[SkillImportance.MENTIONED]),
        experience_min=float(job.experience_min) if job.experience_min is not None else None,
        experience_max=float(job.experience_max) if job.experience_max is not None else None,
        salary_max=job.salary_max,
        salary_currency=job.salary_currency,
        city=job.city,
        location_type=job.location_type,
        employment_type=job.employment_type,
        listed_at=job.listed_at,
    )


def rank_jobs(
    session: Session,
    retrieved: RetrievalResult,
    *,
    ranker: WeightedRanker,
    candidate_id: uuid.UUID | None,
    query: str | None,
    embedding_model: str,
    stage: RankingStage = "features",
    reranker: Reranker | None = None,
    top_k: int = 20,
    now: datetime | None = None,
) -> RankingOutput:
    now = now or datetime.now(UTC)
    timings: dict[str, float] = {}
    t = time.perf_counter()
    ids = [r.job_id for r in retrieved.jobs]
    jobs = {
        j.id: j
        for j in session.scalars(
            select(Job)
            .where(Job.id.in_(ids))
            .options(selectinload(Job.skills).joinedload(JobSkill.skill))
        )
    }
    profile = _load_profile(session, candidate_id) if candidate_id else None
    cand = candidate_facts(profile)
    similarities = _similarities(session, retrieved, ids, embedding_model)
    max_fused = max((r.fused_score for r in retrieved.jobs), default=0.0) or 1.0

    ranked: list[RankedJob] = []
    for r in retrieved.jobs:
        job = jobs[r.job_id]
        jf = job_facts(job)
        fv: FeatureVector = compute_features(
            cand,
            jf,
            semantic_similarity=similarities.get(r.job_id),
            retrieval_score=r.fused_score / max_fused,
            now=now,
        )
        contrib = ranker.contributions(fv)
        names = {js.skill_id: js.skill.name for js in job.skills}
        s1 = sum(contrib.values())
        ranked.append(
            RankedJob(
                job_id=job.id,
                title=job.title,
                company=job.company,
                score=s1,
                stage1_score=s1,
                cross_encoder_score=None,
                features=fv.values,
                contributions=contrib,
                missing_features=sorted(fv.missing),
                explanation=explain(fv, contrib, jf, names, has_candidate=profile is not None),
                lexical_rank=r.lexical_rank,
                semantic_rank=r.semantic_rank,
            )
        )
    # Ties broken by retrieval order (stable sort), so output is deterministic.
    ranked.sort(key=lambda x: -x.stage1_score)
    timings["stage1"] = _ms(t)

    if stage == "features+cross_encoder" and reranker is not None and ranked:
        t = time.perf_counter()
        head = ranked[:CROSS_ENCODER_TOP_N]
        left = query or (candidate_text(profile) if profile else "")
        logits = reranker.score([(left, job_text(jobs[x.job_id])) for x in head])
        for item, raw in zip(head, logits, strict=True):
            item.cross_encoder_score = raw
            item.score = (
                1 - CROSS_ENCODER_BLEND
            ) * item.stage1_score + CROSS_ENCODER_BLEND * sigmoid(raw)
        head.sort(key=lambda x: -x.score)
        ranked = head + ranked[CROSS_ENCODER_TOP_N:]
        timings["cross_encoder"] = _ms(t)

    return RankingOutput(ranked[:top_k], stage, ranker.version, timings)


def _similarities(
    session: Session, retrieved: RetrievalResult, ids: list[uuid.UUID], model: str
) -> dict[uuid.UUID, float]:
    """Cosine for every retrieved job, including ones found only by lexical search."""
    sims = {r.job_id: r.similarity for r in retrieved.jobs if r.similarity is not None}
    missing = [i for i in ids if i not in sims]
    if missing and retrieved.query_vector is not None:
        q = np.asarray(retrieved.query_vector, dtype=np.float32)
        rows = session.execute(
            select(JobEmbedding.job_id, JobEmbedding.embedding).where(
                JobEmbedding.job_id.in_(missing), JobEmbedding.embedding_model == model
            )
        ).all()
        for job_id, vec in rows:
            sims[job_id] = float(np.asarray(vec, dtype=np.float32) @ q)
    return sims


def _load_profile(session: Session, candidate_id: uuid.UUID) -> CandidateProfile | None:
    return session.scalar(
        select(CandidateProfile)
        .where(CandidateProfile.id == candidate_id)
        .options(selectinload(CandidateProfile.skills).joinedload(CandidateSkill.skill))
    )


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)
