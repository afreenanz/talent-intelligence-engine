import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin, pg_enum_values
from app.db.enums import MemorySource, MemoryType


class AgentMemory(UUIDPrimaryKeyMixin, Base):
    """Long-term candidate preferences (memory-design.md). One row per (type, key).

    Explicit rows are stated by the candidate (settings page or a confirmed agent action).
    Derived rows are inferred from behaviour in Milestone 5B and never override explicit ones.
    """

    __tablename__ = "agent_memory"
    __table_args__ = (
        UniqueConstraint("candidate_id", "memory_type", "memory_key", name="uq_agent_memory_key"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
    )

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False
    )
    memory_type: Mapped[MemoryType] = mapped_column(
        Enum(MemoryType, name="memory_type", values_callable=pg_enum_values), nullable=False
    )
    memory_key: Mapped[str] = mapped_column(Text, nullable=False)
    memory_value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[MemorySource] = mapped_column(
        Enum(MemorySource, name="memory_source", values_callable=pg_enum_values), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
