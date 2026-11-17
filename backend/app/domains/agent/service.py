"""Agent use cases: chat turn, confirmation, conversation history.

Two persistence paths, on purpose (ADR-009): LangGraph checkpoints hold execution state
(needed to pause and resume at a confirmation); the `messages` table holds the user-facing
history the UI reads. A turn's user message is stored first, its reply when the turn ends.
"""

import uuid
from typing import Any

import structlog
from langgraph.types import Command
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, UpstreamUnavailableError
from app.db.enums import MessageRole
from app.domains.agent import tools as agent_tools
from app.domains.agent.checkpointer import get_checkpointer
from app.domains.agent.graph import build_graph, turn_input
from app.domains.agent.models import Conversation, Message
from app.domains.agent.prompts import AGENT_PROMPT_VERSION
from app.domains.agent.schemas import ChatResponse, PendingAction, ToolCallTrace
from app.domains.candidates import service as candidates
from app.domains.preferences import service as prefs
from app.integrations.llm.base import LLMError, ToolCallingLLM

log = structlog.get_logger(__name__)


def _context_text(session: Session, user_id: uuid.UUID, candidate_id: uuid.UUID) -> str:
    p = candidates.get_my_profile(session, user_id)
    effective = prefs.effective_preferences(session, candidate_id)
    lines = [
        f"- Name: {p.full_name or 'unknown'}",
        f"- Experience: {'unknown' if p.experience_years is None else p.experience_years} years",
        f"- Location: {p.location or 'unknown'}",
        f"- Skills: {', '.join(cs.skill.name for cs in p.skills) or 'none listed'}",
    ]
    for key, row in sorted(effective.items()):
        kind = "stated" if row.memory_type.value == "explicit_preference" else "learned"
        value = {k: v for k, v in row.memory_value.items() if k != "evidence"}
        lines.append(f"- Preference {key} ({kind}): {value}")
    return "\n".join(lines)


def _graph(
    session: Session,
    user_id: uuid.UUID,
    candidate_id: uuid.UUID,
    llm: ToolCallingLLM,
    tool_ctx: agent_tools.ToolContext,
) -> Any:
    return build_graph(
        llm, tool_ctx, lambda: _context_text(session, user_id, candidate_id), get_checkpointer()
    )


def _owned(session: Session, candidate_id: uuid.UUID, conversation_id: uuid.UUID) -> Conversation:
    conv = session.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id, Conversation.candidate_id == candidate_id
        )
    )
    if conv is None:
        raise NotFoundError("Conversation not found")
    return conv


def _config(conversation_id: uuid.UUID) -> dict[str, Any]:
    return {"configurable": {"thread_id": str(conversation_id)}}


def awaiting_confirmation(conversation_id: uuid.UUID) -> bool:
    snapshot = get_checkpointer().get_tuple(_config(conversation_id))  # type: ignore[arg-type]
    if snapshot is None:
        return False
    return any(w[1] == "__interrupt__" for w in snapshot.pending_writes or [])


def _run(graph: Any, payload: Any, conversation_id: uuid.UUID) -> dict[str, Any]:
    try:
        result: dict[str, Any] = graph.invoke(payload, _config(conversation_id))
        return result
    except LLMError as exc:
        log.warning("agent_llm_error", conversation_id=str(conversation_id), error=str(exc))
        raise UpstreamUnavailableError(
            "The assistant is temporarily unavailable. Try again."
        ) from exc


def _respond(session: Session, conv: Conversation, result: dict[str, Any]) -> ChatResponse:
    trace = [ToolCallTrace(**t) for t in result.get("trace", [])]
    interrupts = result.get("__interrupt__") or []
    if interrupts:
        actions = [PendingAction(**a) for a in interrupts[0].value["actions"]]
        reply = "Please confirm: " + "; ".join(a.summary for a in actions) + "."
        session.add(
            Message(
                conversation_id=conv.id,
                role=MessageRole.ASSISTANT,
                content=reply,
                tool_metadata={
                    "pending_actions": [a.model_dump() for a in actions],
                    "tool_calls": [t.model_dump() for t in trace],
                },
            )
        )
        conv.updated_at = func.now()
        session.commit()
        return ChatResponse(
            conversation_id=conv.id,
            status="awaiting_confirmation",
            reply=reply,
            pending_actions=actions,
            tool_calls=trace,
        )
    final = result["final"]
    usage = [h.get("usage") for h in result.get("history", []) if h.get("role") == "assistant"]
    session.add(
        Message(
            conversation_id=conv.id,
            role=MessageRole.ASSISTANT,
            content=final["text"],
            tool_metadata={
                "tool_calls": [t.model_dump() for t in trace],
                "grounded": final["grounded"],
                "grounding_issues": final["issues"],
                "model_calls": result.get("model_calls"),
                "prompt_version": AGENT_PROMPT_VERSION,
                "usage_last": usage[-1] if usage else None,
            },
        )
    )
    conv.updated_at = func.now()
    session.commit()
    return ChatResponse(
        conversation_id=conv.id,
        status="completed",
        reply=final["text"],
        tool_calls=trace,
        grounded=final["grounded"],
        grounding_issues=final["issues"],
    )


def chat(
    session: Session,
    user_id: uuid.UUID,
    message: str,
    conversation_id: uuid.UUID | None,
    llm: ToolCallingLLM,
    tool_ctx: agent_tools.ToolContext,
) -> ChatResponse:
    candidate_id = tool_ctx.candidate_id
    if conversation_id is None:
        conv = Conversation(candidate_id=candidate_id, title=message.strip()[:60])
        session.add(conv)
        session.flush()
    else:
        conv = _owned(session, candidate_id, conversation_id)
        if awaiting_confirmation(conv.id):
            raise ConflictError("Please confirm or decline the pending action first")
    session.add(Message(conversation_id=conv.id, role=MessageRole.USER, content=message))
    session.commit()
    graph = _graph(session, user_id, candidate_id, llm, tool_ctx)
    return _respond(session, conv, _run(graph, turn_input(message), conv.id))


def confirm(
    session: Session,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    approved: bool,
    llm: ToolCallingLLM,
    tool_ctx: agent_tools.ToolContext,
) -> ChatResponse:
    conv = _owned(session, tool_ctx.candidate_id, conversation_id)
    if not awaiting_confirmation(conv.id):
        raise ConflictError("Nothing is waiting for confirmation in this conversation")
    session.add(
        Message(
            conversation_id=conv.id,
            role=MessageRole.USER,
            content="Confirmed." if approved else "Declined.",
        )
    )
    session.commit()
    graph = _graph(session, user_id, tool_ctx.candidate_id, llm, tool_ctx)
    return _respond(session, conv, _run(graph, Command(resume={"approved": approved}), conv.id))


def list_conversations(session: Session, candidate_id: uuid.UUID) -> list[Conversation]:
    return list(
        session.scalars(
            select(Conversation)
            .where(Conversation.candidate_id == candidate_id)
            .order_by(Conversation.updated_at.desc())
        )
    )


def get_conversation(
    session: Session, candidate_id: uuid.UUID, conversation_id: uuid.UUID
) -> tuple[Conversation, list[Message]]:
    conv = _owned(session, candidate_id, conversation_id)
    msgs = list(
        session.scalars(
            select(Message).where(Message.conversation_id == conv.id).order_by(Message.seq)
        )
    )
    return conv, msgs


def delete_conversation(
    session: Session, candidate_id: uuid.UUID, conversation_id: uuid.UUID
) -> None:
    conv = _owned(session, candidate_id, conversation_id)
    session.delete(conv)
    session.commit()
    get_checkpointer().delete_thread(str(conversation_id))  # execution state goes too
