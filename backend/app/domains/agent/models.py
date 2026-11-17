"""User-facing conversation history (ADR-009). LangGraph's own checkpoint tables hold execution
state and live in a separate `langgraph` schema; these tables are what the UI reads."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Identity, Index, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, pg_enum_values
from app.db.enums import MessageRole


class Conversation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "conversations"
    __table_args__ = (Index("ix_conversations_candidate_updated", "candidate_id", "updated_at"),)

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)


class Message(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_conversation_seq", "conversation_id", "seq"),)

    # Ordering key. created_at can't be used: now() is the *transaction* start time, so messages
    # written in one transaction share a timestamp and would come back in random (UUID) order.
    seq: Mapped[int] = mapped_column(BigInteger, Identity(), nullable=False, unique=True)

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[MessageRole] = mapped_column(
        Enum(MessageRole, name="message_role", values_callable=pg_enum_values), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Tool calls made for this turn, grounding result, token usage: for audit and evaluation.
    tool_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
