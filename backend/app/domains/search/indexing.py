"""Incremental embedding of jobs and candidates.

A vector is (re)computed only when the text it was built from changed. That text is defined by
a versioned template, and its hash is stored alongside the vector:

    embedding_hash = sha256(TEMPLATE_VERSION | text)

Re-running `embed-jobs` on an unchanged corpus therefore does no model work at all.
"""

import hashlib
import time
import uuid
from dataclasses import dataclass

import numpy as np
import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.enums import JobStatus
from app.domains.candidates.models import CandidateProfile, CandidateSkill
from app.domains.jobs.models import Job
from app.domains.search.models import CandidateEmbedding, JobEmbedding
from app.integrations.embeddings.base import Embedder, Vector

log = structlog.get_logger(__name__)

JOB_TEMPLATE_VERSION = "job_text_v1"
CANDIDATE_TEMPLATE_VERSION = "candidate_text_v1"
DESCRIPTION_CHARS = 1500  # keeps documents within the models' 256-512 token window


def job_text(job: Job) -> str:
    parts = [
        job.title,
        f"Company: {job.company}",
        f"Skills: {job.skills_text}" if job.skills_text else "",
        f"Location: {job.city or job.location}" if (job.city or job.location) else "",
        job.description[:DESCRIPTION_CHARS],
    ]
    return "\n".join(p for p in parts if p)


def candidate_text(profile: CandidateProfile) -> str:
    skills = ", ".join(cs.skill.name for cs in profile.skills)
    projects = "; ".join(
        f"{p.get('name', '')} ({', '.join(p.get('technologies') or [])})" for p in profile.projects
    )
    fields = "; ".join(
        " ".join(filter(None, [e.get("degree"), e.get("field_of_study")]))
        for e in profile.education
    )
    parts = [
        profile.profile_summary or "",
        f"Skills: {skills}" if skills else "",
        f"Projects: {projects}" if projects else "",
        f"Education: {fields}" if fields.strip("; ") else "",
    ]
    return "\n".join(p for p in parts if p)


def text_hash(template_version: str, text: str) -> str:
    return hashlib.sha256(f"{template_version}|{text}".encode()).hexdigest()


@dataclass
class EmbedJobsResult:
    considered: int
    embedded: int
    skipped_unchanged: int
    seconds: float


def embed_jobs(
    session: Session, embedder: Embedder, *, batch_size: int = 64, include_inactive: bool = False
) -> EmbedJobsResult:
    started = time.perf_counter()
    model = embedder.spec.name
    statuses = list(JobStatus) if include_inactive else [JobStatus.ACTIVE]
    existing = dict(
        session.execute(
            select(JobEmbedding.job_id, JobEmbedding.content_hash).where(
                JobEmbedding.embedding_model == model
            )
        ).all()
    )
    considered = 0
    pending: list[tuple[uuid.UUID, str, str]] = []
    for job in session.scalars(select(Job).where(Job.status.in_(statuses))):
        considered += 1
        text = job_text(job)
        h = text_hash(JOB_TEMPLATE_VERSION, text)
        if existing.get(job.id) != h:
            pending.append((job.id, text, h))

    for i in range(0, len(pending), batch_size):
        batch = pending[i : i + batch_size]
        vectors = embedder.encode_documents([t for _, t, _ in batch], batch_size=batch_size)
        _upsert_job_vectors(session, model, batch, vectors)
        session.commit()
        log.info("job_embeddings_batch", done=min(i + batch_size, len(pending)), total=len(pending))

    return EmbedJobsResult(
        considered=considered,
        embedded=len(pending),
        skipped_unchanged=considered - len(pending),
        seconds=round(time.perf_counter() - started, 2),
    )


def _upsert_job_vectors(
    session: Session, model: str, batch: list[tuple[uuid.UUID, str, str]], vectors: Vector
) -> None:
    rows = [
        {"job_id": jid, "embedding_model": model, "embedding": vec.tolist(), "content_hash": h}
        for (jid, _, h), vec in zip(batch, vectors, strict=True)
    ]
    stmt = insert(JobEmbedding).values(rows)
    session.execute(
        stmt.on_conflict_do_update(
            constraint="uq_job_embeddings_job_model",
            set_={"embedding": stmt.excluded.embedding, "content_hash": stmt.excluded.content_hash},
        )
    )


def candidate_vector(
    session: Session, profile: CandidateProfile, embedder: Embedder
) -> Vector | None:
    """Return the candidate's embedding, recomputing it only if their profile text changed.

    Returns None for an empty profile (cold start): there is nothing meaningful to embed.
    """
    # Make sure skills are loaded with their names.
    _ = [cs.skill.name for cs in profile.skills if isinstance(cs, CandidateSkill)]
    text = candidate_text(profile)
    if not text.strip():
        return None
    model = embedder.spec.name
    h = text_hash(CANDIDATE_TEMPLATE_VERSION, text)
    row = session.scalar(
        select(CandidateEmbedding).where(
            CandidateEmbedding.candidate_id == profile.id,
            CandidateEmbedding.embedding_model == model,
        )
    )
    if row is not None and row.content_hash == h:
        cached: Vector = np.asarray(row.embedding, dtype=np.float32)
        return cached
    vector: Vector = embedder.encode_documents([text])[0]
    stmt = insert(CandidateEmbedding).values(
        candidate_id=profile.id, embedding_model=model, embedding=vector.tolist(), content_hash=h
    )
    session.execute(
        stmt.on_conflict_do_update(
            constraint="uq_candidate_embeddings_model",
            set_={"embedding": stmt.excluded.embedding, "content_hash": stmt.excluded.content_hash},
        )
    )
    session.commit()
    return vector
