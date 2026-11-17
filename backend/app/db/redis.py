"""Redis client. Milestone 1 uses it only for readiness checks; caching comes in Milestone 9."""

from functools import lru_cache

from redis import Redis

from app.core.config import get_settings


@lru_cache
def get_redis() -> "Redis":
    return Redis.from_url(get_settings().redis_url, socket_timeout=2, socket_connect_timeout=2)
