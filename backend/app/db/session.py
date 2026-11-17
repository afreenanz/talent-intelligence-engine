"""Engine and session lifecycle.

One Session per request (FastAPI dependency). Services own transaction boundaries and call
`session.commit()`. The dependency guarantees that a failed request rolls back and that the
session is always closed.
"""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,  # transparently replace connections dropped by the server
        pool_size=5,
        max_overflow=10,
    )


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    # expire_on_commit=False: objects stay readable after commit (we serialise them into the
    # response after the service has committed).
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_db() -> Iterator[Session]:
    session = get_sessionmaker()()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
