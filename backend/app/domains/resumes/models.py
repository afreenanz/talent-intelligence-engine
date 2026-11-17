import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CHAR, DateTime, Enum, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, pg_enum_values
from app.db.enums import ResumeStatus


class Resume(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "resumes"
    __table_args__ = (Index("ix_resumes_candidate_created", "candidate_id", "created_at"),)

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False
    )
    # Server-generated path; the client-supplied filename is never used to build paths.
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    file_sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer)

    extracted_text: Mapped[str | None] = mapped_column(Text)
    # Post-processed extraction (ParsedResume). Never copied into the profile without review.
    parsed_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    parsing_status: Mapped[ResumeStatus] = mapped_column(
        Enum(ResumeStatus, name="resume_status", values_callable=pg_enum_values),
        nullable=False,
        server_default=ResumeStatus.PENDING.value,
    )
    parsing_error: Mapped[str | None] = mapped_column(Text)

    # LLM call metadata: feeds cost/latency reporting in the evaluation milestone.
    llm_model: Mapped[str | None] = mapped_column(Text)
    llm_latency_ms: Mapped[int | None] = mapped_column(Integer)
    llm_input_tokens: Mapped[int | None] = mapped_column(Integer)
    llm_output_tokens: Mapped[int | None] = mapped_column(Integer)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
