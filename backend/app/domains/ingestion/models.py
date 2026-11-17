import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin, pg_enum_values
from app.db.enums import IngestionMode, IngestionRunStatus


def _counter() -> Mapped[int]:
    return mapped_column(Integer, nullable=False, server_default=text("0"))


class IngestionRun(UUIDPrimaryKeyMixin, Base):
    """Audit record of one import: what came in and what happened to it."""

    __tablename__ = "ingestion_runs"

    source: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[IngestionMode] = mapped_column(
        Enum(IngestionMode, name="ingestion_mode", values_callable=pg_enum_values), nullable=False
    )
    file_name: Mapped[str | None] = mapped_column(Text)
    status: Mapped[IngestionRunStatus] = mapped_column(
        Enum(IngestionRunStatus, name="ingestion_run_status", values_callable=pg_enum_values),
        nullable=False,
    )
    received: Mapped[int] = _counter()
    inserted: Mapped[int] = _counter()
    updated: Mapped[int] = _counter()
    unchanged: Mapped[int] = _counter()
    duplicates: Mapped[int] = _counter()
    failed: Mapped[int] = _counter()
    expired: Mapped[int] = _counter()
    removed: Mapped[int] = _counter()
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IngestionError(Base):
    """A record that failed. The raw payload is kept so it can be retried without re-importing."""

    __tablename__ = "ingestion_errors"
    __table_args__ = (
        Index(
            "ix_ingestion_errors_unresolved",
            "run_id",
            postgresql_where=text("resolved_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ingestion_runs.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str] = mapped_column(Text, nullable=False)
    external_id: Mapped[str | None] = mapped_column(Text)
    raw_record: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    error_type: Mapped[str] = mapped_column(Text, nullable=False)  # "validation" | "database"
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    # Validation errors won't fix themselves; transient DB errors might on retry.
    retryable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
