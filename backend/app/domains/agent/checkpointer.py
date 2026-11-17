"""LangGraph Postgres checkpointer, in its own schema.

Connection settings required by PostgresSaver (verified in its source, 2026-11-18): autocommit
and dict rows. prepare_threshold=0 disables server-side prepared statements, which don't survive
pooled connections reliably. search_path puts LangGraph's tables in the `langgraph` schema
(created by migration a68d84800899), away from Alembic-managed tables.
"""

from functools import lru_cache

from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.core.config import get_settings

SCHEMA = "langgraph"
_pool: ConnectionPool | None = None


@lru_cache
def get_checkpointer() -> PostgresSaver:
    url = get_settings().database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    global _pool
    pool = ConnectionPool(
        url,
        min_size=1,
        max_size=5,
        open=True,
        kwargs={
            "autocommit": True,
            "row_factory": dict_row,
            "prepare_threshold": 0,
            "options": f"-c search_path={SCHEMA}",
        },
    )
    _pool = pool
    saver = PostgresSaver(pool)  # type: ignore[arg-type]
    saver.setup()  # idempotent: creates/migrates LangGraph's tables on first use
    return saver


def close_checkpointer() -> None:
    """Close the pool (app shutdown, end of tests, CLI exit); safe to call when never opened."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
        get_checkpointer.cache_clear()
