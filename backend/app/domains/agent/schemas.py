import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {"message": "Find backend jobs in Bangalore with Python, preferably above 15 LPA"}
            ]
        },
    )

    message: str = Field(min_length=1, max_length=2000)
    conversation_id: uuid.UUID | None = Field(default=None, description="Omit to start a new one")


class ConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [{"approved": True}]})

    approved: bool


class PendingAction(BaseModel):
    tool: str
    arguments: dict[str, Any]
    summary: str


class ToolCallTrace(BaseModel):
    tool: str
    arguments: dict[str, Any]
    ok: bool
    error_code: str | None = None
    confirmed: bool | None = None


class ChatResponse(BaseModel):
    conversation_id: uuid.UUID
    status: Literal["completed", "awaiting_confirmation"]
    reply: str
    pending_actions: list[PendingAction] = Field(default_factory=list)
    tool_calls: list[ToolCallTrace] = Field(default_factory=list)
    grounded: bool | None = None
    grounding_issues: list[str] = Field(default_factory=list)


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: str
    content: str
    tool_metadata: dict[str, Any] | None
    created_at: datetime


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]
    awaiting_confirmation: bool
