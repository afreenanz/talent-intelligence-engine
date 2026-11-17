from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin


class EvaluationRun(UUIDPrimaryKeyMixin, Base):
    """One experiment configuration evaluated on one dataset split.

    Written only by evaluation scripts; the dashboard (Milestone 8) reads from here, so no
    number is ever shown that a script didn't compute.
    """

    __tablename__ = "evaluation_runs"
    __table_args__ = (
        Index("ix_evaluation_runs_experiment_created", "experiment_name", "created_at"),
    )

    experiment_name: Mapped[str] = mapped_column(Text, nullable=False)
    dataset_version: Mapped[str] = mapped_column(Text, nullable=False)
    split: Mapped[str] = mapped_column(Text, nullable=False)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    git_commit: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
