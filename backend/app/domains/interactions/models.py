"""Event log + current-state tables (database-design.md §3.2).

job_interactions is an immutable event log (what happened, in order). saved_jobs and
applications are current state (what is true now). The service writes both in one transaction.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, pg_enum_values
from app.db.enums import ApplicationStatus, InteractionType


class SearchLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "search_logs"
    __table_args__ = (Index("ix_search_logs_candidate_created", "candidate_id", "created_at"),)

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False
    )
    query: Mapped[str | None] = mapped_column(Text)  # None = profile-based recommendations
    filters: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    ranking: Mapped[str] = mapped_column(Text, nullable=False)
    result_count: Mapped[int] = mapped_column(Integer, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class JobInteraction(Base):
    __tablename__ = "job_interactions"
    __table_args__ = (
        Index("ix_job_interactions_candidate_created", "candidate_id", "created_at"),
        Index("ix_job_interactions_job", "job_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False
    )
    # RESTRICT: jobs are expired, never deleted, so history stays interpretable.
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="RESTRICT"), nullable=False
    )
    interaction_type: Mapped[InteractionType] = mapped_column(
        Enum(InteractionType, name="interaction_type", values_callable=pg_enum_values),
        nullable=False,
    )
    search_log_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("search_logs.id", ondelete="SET NULL")
    )
    position: Mapped[int | None] = mapped_column(Integer)  # 1-based rank when shown
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SavedJob(Base):
    __tablename__ = "saved_jobs"

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), primary_key=True
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="RESTRICT"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Application(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint("candidate_id", "job_id", name="uq_applications_candidate_job"),
    )

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="RESTRICT"), nullable=False
    )
    application_status: Mapped[ApplicationStatus] = mapped_column(
        Enum(ApplicationStatus, name="application_status", values_callable=pg_enum_values),
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(Text)
