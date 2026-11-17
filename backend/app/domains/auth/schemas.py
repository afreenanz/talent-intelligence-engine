import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class _StrictModel(BaseModel):
    # Unknown fields are rejected rather than silently ignored, so typos in the client surface
    # and clients can't sneak in fields such as is_admin.
    model_config = ConfigDict(extra="forbid")


class RegisterRequest(_StrictModel):
    email: EmailStr
    # Upper bound guards against a DoS via huge inputs to the (deliberately slow) hash.
    password: str = Field(min_length=10, max_length=128)
    full_name: str | None = Field(default=None, max_length=200)

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.lower()


class LoginRequest(_StrictModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(_StrictModel):
    refresh_token: str = Field(min_length=20, max_length=200)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105  (OAuth2 token type, not a secret)
    expires_in: int = Field(description="Access token lifetime in seconds")


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    is_active: bool
    created_at: datetime
