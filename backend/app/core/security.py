"""Password hashing and token primitives. These are pure functions with no database access.

- Passwords: Argon2id (memory-hard, the OWASP-recommended default).
- Access tokens: short-lived signed JWTs (stateless; verified without a DB lookup of the token).
- Refresh tokens: long random opaque strings. Only their SHA-256 hash is stored, so a
  database leak doesn't hand out usable tokens.
"""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import Settings

_hasher = PasswordHasher()

# Pre-computed hash used when a login email doesn't exist, so the response time doesn't reveal
# whether an account exists (we still pay the full Argon2 verification cost).
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing-equalisation")

ACCESS_TOKEN_TYPE = "access"  # noqa: S105


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    """Constant-work verification. Pass None for a missing user."""
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


@dataclass(frozen=True)
class AccessTokenClaims:
    user_id: uuid.UUID
    expires_at: datetime


class InvalidTokenError(Exception):
    pass


def create_access_token(user_id: uuid.UUID, settings: Settings, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "type": ACCESS_TOKEN_TYPE,
        "iss": settings.jwt_issuer,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_ttl_minutes),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.jwt_secret.get_secret_value(), settings.jwt_algorithm)


def decode_access_token(token: str, settings: Settings) -> AccessTokenClaims:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[settings.jwt_algorithm],  # never trust the token's own "alg" header
            issuer=settings.jwt_issuer,
            options={"require": ["sub", "exp", "iat", "iss", "type"]},
        )
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc
    if payload.get("type") != ACCESS_TOKEN_TYPE:
        raise InvalidTokenError("wrong token type")
    try:
        user_id = uuid.UUID(payload["sub"])
    except ValueError as exc:
        raise InvalidTokenError("malformed subject") from exc
    return AccessTokenClaims(
        user_id=user_id, expires_at=datetime.fromtimestamp(payload["exp"], UTC)
    )


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    # A plain SHA-256 is appropriate here (unlike for passwords): the token has ~384 bits of
    # entropy, so brute-forcing the hash is infeasible and no slow hash is needed.
    return hashlib.sha256(token.encode()).hexdigest()
