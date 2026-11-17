import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.domains.auth.models import RefreshToken, User


def get_user_by_email(session: Session, email: str) -> User | None:
    return session.scalar(select(User).where(User.email == email))


def get_user_by_id(session: Session, user_id: uuid.UUID) -> User | None:
    return session.get(User, user_id)


def get_refresh_token_for_update(session: Session, token_hash: str) -> RefreshToken | None:
    # SELECT ... FOR UPDATE: two concurrent refreshes with the same token serialise on the row,
    # so only one can rotate it; the other then sees it revoked.
    return session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash).with_for_update()
    )


def revoke_all_refresh_tokens(session: Session, user_id: uuid.UUID, now: datetime) -> int:
    result = session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    return int(result.rowcount)  # type: ignore[attr-defined]
