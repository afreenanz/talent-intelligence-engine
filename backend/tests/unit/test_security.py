import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from pydantic import SecretStr

from app.core import security
from app.core.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(jwt_secret=SecretStr("unit-test-secret-" + "x" * 32))


def test_password_hash_roundtrip() -> None:
    h = security.hash_password("s3cret-password")
    assert h.startswith("$argon2id$")
    assert security.verify_password(h, "s3cret-password")
    assert not security.verify_password(h, "wrong-password")


def test_verify_password_with_missing_user_is_false() -> None:
    assert security.verify_password(None, "anything") is False


def test_verify_password_with_garbage_hash_is_false() -> None:
    assert security.verify_password("not-a-hash", "anything") is False


def test_access_token_roundtrip(settings: Settings) -> None:
    uid = uuid.uuid4()
    claims = security.decode_access_token(security.create_access_token(uid, settings), settings)
    assert claims.user_id == uid


def test_expired_access_token_rejected(settings: Settings) -> None:
    past = datetime.now(UTC) - timedelta(hours=1)
    token = security.create_access_token(uuid.uuid4(), settings, now=past)
    with pytest.raises(security.InvalidTokenError):
        security.decode_access_token(token, settings)


def test_token_signed_with_other_secret_rejected(settings: Settings) -> None:
    other = Settings(jwt_secret=SecretStr("a-completely-different-secret-" + "y" * 32))
    token = security.create_access_token(uuid.uuid4(), other)
    with pytest.raises(security.InvalidTokenError):
        security.decode_access_token(token, settings)


def test_unsigned_alg_none_token_rejected(settings: Settings) -> None:
    now = datetime.now(UTC)
    payload = {
        "sub": str(uuid.uuid4()),
        "type": "access",
        "iss": settings.jwt_issuer,
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    token = jwt.encode(payload, key=None, algorithm="none")
    with pytest.raises(security.InvalidTokenError):
        security.decode_access_token(token, settings)


def test_token_with_wrong_type_rejected(settings: Settings) -> None:
    now = datetime.now(UTC)
    payload = {
        "sub": str(uuid.uuid4()),
        "type": "refresh",
        "iss": settings.jwt_issuer,
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    token = jwt.encode(payload, settings.jwt_secret.get_secret_value(), "HS256")
    with pytest.raises(security.InvalidTokenError, match="wrong token type"):
        security.decode_access_token(token, settings)


def test_refresh_tokens_are_random_and_hash_is_stable() -> None:
    a, b = security.generate_refresh_token(), security.generate_refresh_token()
    assert a != b
    assert security.hash_refresh_token(a) == security.hash_refresh_token(a)
    assert len(security.hash_refresh_token(a)) == 64
