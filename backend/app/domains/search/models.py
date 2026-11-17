"""Embedding tables (see database-design.md §3.5).

One row per (entity, model). `content_hash` records exactly which text was embedded, so a
vector is recomputed only when that text changes, or when the embedding template version changes.
"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import CHAR, DateTime, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin

EMBEDDING_DIM = 384  # all configured models are 384-d; another dimension needs its own table


class JobEmbedding(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "job_embeddings"
    __table_args__ = (
        UniqueConstraint("job_id", "embedding_model", name="uq_job_embeddings_job_model"),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    embedding_model: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)
    content_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class CandidateEmbedding(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "candidate_embeddings"
    __table_args__ = (
        UniqueConstraint("candidate_id", "embedding_model", name="uq_candidate_embeddings_model"),
    )

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False
    )
    embedding_model: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)
    content_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
