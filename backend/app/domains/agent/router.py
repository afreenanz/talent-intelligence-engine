import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUser, DbSession
from app.core.errors import UpstreamUnavailableError
from app.core.rate_limit import ASSISTANT, by_user
from app.domains.agent import service
from app.domains.agent.schemas import (
    ChatRequest,
    ChatResponse,
    ConfirmRequest,
    ConversationDetail,
    ConversationOut,
    MessageOut,
)
from app.domains.agent.tools import ToolContext
from app.domains.candidates import service as candidates
from app.domains.ranking.deps import RankerDep
from app.domains.search.deps import EmbedderDep
from app.integrations.llm.base import LLMUnavailableError, ToolCallingLLM
from app.integrations.llm.factory import get_tool_calling_llm

router = APIRouter(prefix="/agent", tags=["agent"])


def llm_dependency() -> ToolCallingLLM:
    try:
        return get_tool_calling_llm()
    except LLMUnavailableError as exc:
        raise UpstreamUnavailableError(
            "The assistant is unavailable: no LLM is configured"
        ) from exc


LLMDep = Annotated[ToolCallingLLM, Depends(llm_dependency)]


def _ctx(
    session: DbSession, user: CurrentUser, embedder: EmbedderDep, ranker: RankerDep
) -> ToolContext:
    profile = candidates.get_my_profile(session, user.id)
    return ToolContext(
        session=session, user_id=user.id, candidate_id=profile.id, embedder=embedder, ranker=ranker
    )


ToolCtxDep = Annotated[ToolContext, Depends(_ctx)]


@router.post("/chat", response_model=ChatResponse, dependencies=[Depends(by_user(ASSISTANT))])
def chat(
    body: ChatRequest, user: CurrentUser, session: DbSession, llm: LLMDep, ctx: ToolCtxDep
) -> ChatResponse:
    """Send a message. If the assistant wants to save a job or change a preference, the response
    has status `awaiting_confirmation`; answer via the confirm endpoint."""
    return service.chat(session, user.id, body.message, body.conversation_id, llm, ctx)


@router.post(
    "/conversations/{conversation_id}/confirm",
    response_model=ChatResponse,
    dependencies=[Depends(by_user(ASSISTANT))],
)
def confirm(
    conversation_id: uuid.UUID,
    body: ConfirmRequest,
    user: CurrentUser,
    session: DbSession,
    llm: LLMDep,
    ctx: ToolCtxDep,
) -> ChatResponse:
    return service.confirm(session, user.id, conversation_id, body.approved, llm, ctx)


@router.get("/conversations", response_model=list[ConversationOut])
def conversations(user: CurrentUser, session: DbSession) -> list[ConversationOut]:
    cid = candidates.get_my_profile(session, user.id).id
    return [ConversationOut.model_validate(c) for c in service.list_conversations(session, cid)]


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def conversation(
    conversation_id: uuid.UUID, user: CurrentUser, session: DbSession
) -> ConversationDetail:
    cid = candidates.get_my_profile(session, user.id).id
    conv, msgs = service.get_conversation(session, cid, conversation_id)
    return ConversationDetail(
        id=conv.id,
        title=conv.title,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        messages=[MessageOut.model_validate(m) for m in msgs],
        awaiting_confirmation=service.awaiting_confirmation(conv.id),
    )


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(conversation_id: uuid.UUID, user: CurrentUser, session: DbSession) -> None:
    cid = candidates.get_my_profile(session, user.id).id
    service.delete_conversation(session, cid, conversation_id)
