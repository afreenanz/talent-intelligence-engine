"""Rate limits, stored in Redis.

Why: once the app is reachable by other people (a shared demo link), each assistant message and
résumé upload spends the owner's Gemini quota, and login is a password-guessing target.

Algorithm: fixed window. One counter per (rule, caller, window), INCR + EXPIRE in one round trip.
Trade-off: a caller can make up to 2x the limit across a window boundary. A sliding window or
token bucket is smoother but needs a Lua script; for abuse protection the simpler scheme is enough.

Failure mode: if Redis is unreachable the limiter fails OPEN (logs and allows). Locking every user
out because a cache is down is worse, for this app, than briefly not limiting.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any, Protocol

import structlog
from fastapi import Depends, Request
from redis.exceptions import RedisError

from app.api.deps import CurrentUser, SettingsDep
from app.core.errors import RateLimitedError
from app.db.redis import get_redis

log = structlog.get_logger()


@dataclass(frozen=True)
class Rule:
    name: str
    limit: int
    window_seconds: int
    message: str


# Limits sized for one person using the app normally, with room to spare.
REGISTER = Rule(
    "register", 10, 3600, "Too many accounts created from this network. Try again later."
)
LOGIN = Rule("login", 20, 900, "Too many sign-in attempts. Wait a few minutes and try again.")
ASSISTANT = Rule("assistant", 40, 3600, "You've sent a lot of messages this hour. Try again later.")
RESUME = Rule("resume", 10, 3600, "Too many résumé uploads this hour. Try again later.")
SEARCH = Rule("search", 120, 60, "Too many searches in a minute. Slow down a little.")


class _Pipeline(Protocol):
    def incr(self, name: str) -> Any: ...
    def expire(self, name: str, time: int, nx: bool = ...) -> Any: ...
    def execute(self) -> list[Any]: ...


class CounterStore(Protocol):
    def pipeline(self) -> _Pipeline: ...


def hit(store: CounterStore, rule: Rule, caller: str, now: float | None = None) -> None:
    """Count one request; raise RateLimitedError if the caller is over the rule's limit."""
    now = time.time() if now is None else now
    window = int(now // rule.window_seconds)
    key = f"rl:{rule.name}:{caller}:{window}"
    try:
        pipe = store.pipeline()
        pipe.incr(key)
        pipe.expire(key, rule.window_seconds, nx=True)
        count = int(pipe.execute()[0])
    except (RedisError, OSError) as exc:
        log.warning("rate_limit_unavailable", rule=rule.name, error=str(exc))
        return
    if count > rule.limit:
        retry_after = max(1, rule.window_seconds - int(now % rule.window_seconds))
        log.info("rate_limited", rule=rule.name, caller=caller, count=count)
        raise RateLimitedError(rule.message, retry_after=retry_after)


def get_counter_store() -> CounterStore:
    return get_redis()


Store = Annotated[CounterStore, Depends(get_counter_store)]


def by_ip(rule: Rule) -> Callable[..., None]:
    """For anonymous endpoints. Behind the bundled nginx, uvicorn's --proxy-headers sets
    request.client to the real client address."""

    def dep(request: Request, settings: SettingsDep, store: Store) -> None:
        if settings.rate_limits_enabled:
            hit(store, rule, f"ip:{request.client.host if request.client else 'unknown'}")

    return dep


def by_user(rule: Rule) -> Callable[..., None]:
    def dep(user: CurrentUser, settings: SettingsDep, store: Store) -> None:
        if settings.rate_limits_enabled:
            hit(store, rule, f"user:{user.id}")

    return dep
