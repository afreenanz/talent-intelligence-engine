"""Explicit preference memory: list, upsert (returns previous value), delete.

Precedence rule (memory-design.md rule 4): for the same key, an explicit preference always
wins over a derived one. Derived rows are written only by the Milestone 5B job.
"""

import uuid
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.db.enums import MemorySource, MemoryType
from app.domains.preferences.models import AgentMemory
from app.domains.preferences.schemas import PreferenceChange, PreferenceKey, validate_value


def list_preferences(session: Session, candidate_id: uuid.UUID) -> list[AgentMemory]:
    return list(
        session.scalars(
            select(AgentMemory)
            .where(AgentMemory.candidate_id == candidate_id)
            .order_by(AgentMemory.memory_type, AgentMemory.memory_key)
        )
    )


def effective_preferences(session: Session, candidate_id: uuid.UUID) -> dict[str, AgentMemory]:
    """One row per key: explicit if present, otherwise derived."""
    out: dict[str, AgentMemory] = {}
    for row in list_preferences(session, candidate_id):
        if row.memory_key not in out or row.memory_type is MemoryType.EXPLICIT_PREFERENCE:
            out[row.memory_key] = row
    return out


def set_explicit(
    session: Session,
    candidate_id: uuid.UUID,
    key: PreferenceKey,
    value: dict[str, Any],
    source: MemorySource = MemorySource.SETTINGS,
) -> PreferenceChange:
    clean = validate_value(key, value)
    previous = session.scalar(
        select(AgentMemory.memory_value)
        .where(
            AgentMemory.candidate_id == candidate_id,
            AgentMemory.memory_key == key.value,
            AgentMemory.memory_type == MemoryType.EXPLICIT_PREFERENCE,
        )
        .with_for_update()
    )
    stmt = insert(AgentMemory).values(
        candidate_id=candidate_id,
        memory_type=MemoryType.EXPLICIT_PREFERENCE,
        memory_key=key.value,
        memory_value=clean,
        confidence=1.0,
        source=source,
    )
    session.execute(
        stmt.on_conflict_do_update(
            constraint="uq_agent_memory_key",
            set_={
                "memory_value": stmt.excluded.memory_value,
                "source": stmt.excluded.source,
                "confidence": 1.0,
                # onupdate= only fires for ORM updates, not INSERT ... ON CONFLICT DO UPDATE
                "updated_at": func.now(),
            },
        )
    )
    session.commit()
    return PreferenceChange(key=key.value, value=clean, previous=previous, created=previous is None)


def delete_explicit(session: Session, candidate_id: uuid.UUID, key: PreferenceKey) -> None:
    removed = session.execute(
        delete(AgentMemory)
        .where(
            AgentMemory.candidate_id == candidate_id,
            AgentMemory.memory_key == key.value,
            AgentMemory.memory_type == MemoryType.EXPLICIT_PREFERENCE,
        )
        .returning(AgentMemory.id)
    ).first()
    if removed is None:
        raise NotFoundError(f"No saved preference for {key.value!r}")
    session.commit()
