"""The three retrieval strategies. Each is independent, takes the same filters, and returns ranks.

LEXICAL: PostgreSQL full-text search.
  - Query: plainto_tsquery terms OR-ed together. websearch/plain tsqueries AND every term,
    so a natural query like "python backend bangalore startup" would require all four words
    and usually return nothing. OR + ranking is how classic ranked retrieval (e.g. BM25) behaves.
  - Score: ts_rank_cd(search_vector, query, 1|32), cover density weighted by A-D field weights,
    normalised by log document length and scaled to [0, 1).
  - Not BM25: no IDF (a common term weighs as much as a rare one) and no term saturation.

DENSE: pgvector cosine distance (`<=>`) on L2-normalised embeddings.
  - Exact scan at this corpus size. An HNSW index plus `hnsw.iterative_scan` is the planned
    upgrade once benchmarks show the scan is slow (see docs/retrieval-engine.md).

HYBRID: Reciprocal Rank Fusion of the two ranked lists (see fusion.py).
"""

import uuid
from typing import Any

from sqlalchemy import Select, Text, cast, func, or_, select, text
from sqlalchemy.dialects.postgresql import TSQUERY
from sqlalchemy.orm import Session

from app.db.enums import JobStatus
from app.domains.jobs.models import Job
from app.domains.search.models import JobEmbedding
from app.domains.search.schemas import JobFilters
from app.integrations.embeddings.base import Vector


def apply_filters(stmt: Select[Any], f: JobFilters) -> Select[Any]:
    stmt = stmt.where(Job.status == JobStatus.ACTIVE)
    if f.city:
        stmt = stmt.where(func.lower(Job.city) == f.city.lower())
    if f.location_type:
        stmt = stmt.where(Job.location_type == f.location_type)
    if f.employment_type:
        stmt = stmt.where(Job.employment_type == f.employment_type)
    if f.min_salary is not None:
        # Keep unknown salaries; drop only jobs *known* to pay less (or in another currency).
        stmt = stmt.where(
            or_(
                Job.salary_max.is_(None),
                (Job.salary_currency == f.salary_currency) & (Job.salary_max >= f.min_salary),
            )
        )
    if f.max_experience_required is not None:
        stmt = stmt.where(
            or_(Job.experience_min.is_(None), Job.experience_min <= f.max_experience_required)
        )
    if f.company:
        stmt = stmt.where(Job.company.icontains(f.company, autoescape=True))
    return stmt


def lexical_search(
    session: Session, query: str, filters: JobFilters, limit: int
) -> list[tuple[uuid.UUID, float]]:
    # plainto_tsquery stems and drops stop words, giving e.g. 'python' & 'backend'. We swap & for |
    # and cast straight back to tsquery. Passing it through to_tsquery again would re-stem the
    # already-stemmed lexemes.
    tsquery = cast(
        func.replace(cast(func.plainto_tsquery("english", query), Text), "&", "|"), TSQUERY
    )
    score = func.ts_rank_cd(Job.search_vector, tsquery, 1 | 32).label("score")
    stmt = select(Job.id, score).where(Job.search_vector.op("@@")(tsquery))
    stmt = apply_filters(stmt, filters).order_by(score.desc(), Job.id).limit(limit)
    return [(row.id, float(row.score)) for row in session.execute(stmt)]


def dense_search(
    session: Session, vector: Vector, model: str, filters: JobFilters, limit: int
) -> list[tuple[uuid.UUID, float]]:
    distance = JobEmbedding.embedding.cosine_distance(vector.tolist()).label("distance")
    stmt = (
        select(Job.id, distance)
        .join(JobEmbedding, JobEmbedding.job_id == Job.id)
        .where(JobEmbedding.embedding_model == model)
    )
    stmt = apply_filters(stmt, filters).order_by(distance, Job.id).limit(limit)
    # Only relevant once an HNSW index exists; harmless otherwise. Keeps filtered ANN queries
    # from returning fewer than `limit` rows (pgvector >= 0.8).
    session.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
    return [(row.id, 1.0 - float(row.distance)) for row in session.execute(stmt)]
