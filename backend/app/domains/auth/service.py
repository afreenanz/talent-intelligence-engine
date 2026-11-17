"""Authentication use cases: register, login, refresh-token rotation, logout."""

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import Settings
from app.core.errors import AuthenticationError, ConflictError
from app.domains.auth import repository
from app.domains.auth.models import RefreshToken, User
from app.domains.auth.schemas import RegisterRequest, TokenPair
from app.domains.candidates.models import CandidateProfile

log = structlog.get_logger(__name__)

# One message for every login failure, so responses don't reveal whether an email is registered.
_INVALID_CREDENTIALS = "Invalid email or password"


def register(session: Session, data: RegisterRequest) -> User:
    """Create a user and their (empty) candidate profile atomically."""
    user = User(email=data.email, password_hash=security.hash_password(data.password))
    session.add(user)
    try:
        session.flush()  # assigns user.id; raises on duplicate email
        session.add(CandidateProfile(user_id=user.id, full_name=data.full_name))
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        # Trade-off: a 409 reveals that the email exists. Accepted for a job platform where
        # the sign-up UX needs it; login itself never reveals it. Rate limiting mitigates
        # enumeration (Milestone 9).
        raise ConflictError("An account with this email already exists") from exc
    log.info("user_registered", user_id=str(user.id))
    return user


def login(session: Session, email: str, password: str, settings: Settings) -> TokenPair:
    user = repository.get_user_by_email(session, email.lower())
    # verify_password does a full Argon2 verification even when the user doesn't exist (timing).
    password_ok = security.verify_password(user.password_hash if user else None, password)
    if user is None or not password_ok:
        log.info("login_failed")
        raise AuthenticationError(_INVALID_CREDENTIALS)
    if not user.is_active:
        raise AuthenticationError(_INVALID_CREDENTIALS)
    if security.password_needs_rehash(user.password_hash):
        user.password_hash = security.hash_password(password)
    tokens = _issue_tokens(session, user.id, settings)
    session.commit()
    log.info("login_succeeded", user_id=str(user.id))
    return tokens


def refresh(session: Session, refresh_token: str, settings: Settings) -> TokenPair:
    """Rotate a refresh token. Reuse of an already-rotated token revokes all of the user's tokens.

    Why: if an attacker steals a refresh token and either party uses it after the other did,
    the second use hits a revoked row. We can't tell who is legitimate, so we log everyone out.
    """
    now = datetime.now(UTC)
    row = repository.get_refresh_token_for_update(
        session, security.hash_refresh_token(refresh_token)
    )
    if row is None:
        raise AuthenticationError("Invalid refresh token")
    if row.revoked_at is not None:
        revoked = repository.revoke_all_refresh_tokens(session, row.user_id, now)
        session.commit()
        log.warning("refresh_token_reuse_detected", user_id=str(row.user_id), revoked=revoked)
        raise AuthenticationError("Invalid refresh token")
    if row.expires_at <= now:
        raise AuthenticationError("Refresh token expired")
    user = repository.get_user_by_id(session, row.user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("Invalid refresh token")

    row.revoked_at = now
    tokens = _issue_tokens(session, row.user_id, settings, now=now)
    session.commit()
    return tokens


def logout(session: Session, refresh_token: str) -> None:
    """Revoke one refresh token. Idempotent: unknown or already-revoked tokens are a no-op."""
    row = repository.get_refresh_token_for_update(
        session, security.hash_refresh_token(refresh_token)
    )
    if row is not None and row.revoked_at is None:
        row.revoked_at = datetime.now(UTC)
        session.commit()


def _issue_tokens(
    session: Session, user_id: uuid.UUID, settings: Settings, now: datetime | None = None
) -> TokenPair:
    now = now or datetime.now(UTC)
    raw_refresh = security.generate_refresh_token()
    session.add(
        RefreshToken(
            user_id=user_id,
            token_hash=security.hash_refresh_token(raw_refresh),
            expires_at=now + timedelta(days=settings.refresh_token_ttl_days),
        )
    )
    return TokenPair(
        access_token=security.create_access_token(user_id, settings, now=now),
        refresh_token=raw_refresh,
        expires_in=settings.access_token_ttl_minutes * 60,
    )
