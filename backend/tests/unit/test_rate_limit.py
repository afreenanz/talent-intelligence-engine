from typing import Any

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core.errors import RateLimitedError
from app.core.rate_limit import Rule, hit


class FakeStore:
    """Just enough of a Redis pipeline: INCR + EXPIRE(NX), executed together."""

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.ttls: dict[str, int] = {}
        self.down = False

    def pipeline(self) -> "FakeStore":
        self._ops: list[tuple[str, str, int]] = []
        return self

    def incr(self, name: str) -> None:
        self._ops.append(("incr", name, 0))

    def expire(self, name: str, time: int, nx: bool = False) -> None:
        self._ops.append(("expire", name, time))

    def execute(self) -> list[Any]:
        if self.down:
            raise RedisConnectionError("down")
        out: list[Any] = []
        for op, name, t in self._ops:
            if op == "incr":
                self.counts[name] = self.counts.get(name, 0) + 1
                out.append(self.counts[name])
            else:
                self.ttls.setdefault(name, t)
                out.append(True)
        return out


RULE = Rule("t", limit=3, window_seconds=60, message="slow down")


def test_allows_up_to_the_limit_then_blocks_with_time_to_reset() -> None:
    store = FakeStore()
    for _ in range(3):
        hit(store, RULE, "user:1", now=1000.0)
    with pytest.raises(RateLimitedError) as e:
        hit(store, RULE, "user:1", now=1010.0)
    # window = [960, 1020): 10 seconds left at t=1010
    assert e.value.retry_after == 10
    assert e.value.status_code == 429
    assert list(store.ttls.values()) == [60]  # key expires with its window


def test_callers_and_windows_are_independent() -> None:
    store = FakeStore()
    for _ in range(3):
        hit(store, RULE, "user:1", now=1000.0)
    hit(store, RULE, "user:2", now=1000.0)  # someone else
    hit(store, RULE, "user:1", now=1021.0)  # next window


def test_fails_open_when_redis_is_down() -> None:
    store = FakeStore()
    store.down = True
    for _ in range(10):
        hit(store, RULE, "user:1", now=1000.0)  # no exception
