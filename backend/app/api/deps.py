"""Shared FastAPI dependencies: DB session, settings, authenticated user."""

from typing import Annotated

import structlog
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AuthenticationError
from app.core.security import InvalidTokenError, decode_access_token
from app.db.session import get_db
from app.domains.auth.models import User
from app.domains.auth.repository import get_user_by_id

# auto_error=False so a missing header goes through our error envelope, not FastAPI's default.
_bearer = HTTPBearer(auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_current_user(
    session: DbSession,
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationError("Missing bearer token")
    try:
        claims = decode_access_token(credentials.credentials, settings)
    except InvalidTokenError as exc:
        raise AuthenticationError("Invalid or expired access token") from exc
    # DB lookup on every request: a deactivated or deleted user is locked out immediately,
    # instead of after the access token expires. Cost: one PK lookup.
    user = get_user_by_id(session, claims.user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("Invalid or expired access token")
    structlog.contextvars.bind_contextvars(user_id=str(user.id))
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
