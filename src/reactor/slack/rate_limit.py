from __future__ import annotations

import time
from collections import deque
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, cast


class RedisRateLimitClient(Protocol):
    def eval(
        self,
        script: str,
        numkeys: int,
        *keys_and_args: Any,
    ) -> Awaitable[object]: ...


@dataclass
class InMemorySlackUserRateLimiter:
    max_requests_per_window: int = 10
    window_seconds: float = 60.0
    max_users: int = 50_000
    now: Callable[[], float] = time.monotonic

    def __post_init__(self) -> None:
        if self.max_requests_per_window <= 0:
            raise ValueError("max_requests_per_window must be positive")
        if self.window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        if self.max_users <= 0:
            raise ValueError("max_users must be positive")
        self._windows: dict[str, deque[float]] = {}

    def try_acquire(self, tenant_id: str, user_id: str) -> bool:
        current_time = self.now()
        self._cleanup(current_time)
        window = self._windows.setdefault(rate_limit_identity(tenant_id, user_id), deque())
        self._purge_expired(window, current_time)
        if len(window) >= self.max_requests_per_window:
            return False
        window.append(current_time)
        return True

    def _purge_expired(self, window: deque[float], current_time: float) -> None:
        cutoff = current_time - self.window_seconds
        while window and window[0] < cutoff:
            window.popleft()

    def _cleanup(self, current_time: float) -> None:
        if len(self._windows) <= self.max_users:
            return
        empty_or_expired: list[str] = []
        for user_id, window in self._windows.items():
            self._purge_expired(window, current_time)
            if not window:
                empty_or_expired.append(user_id)
        for user_id in empty_or_expired:
            self._windows.pop(user_id, None)


@dataclass
class RedisSlackUserRateLimiter:
    redis: RedisRateLimitClient
    max_requests_per_minute: int = 10
    now_millis: Callable[[], int] = lambda: int(time.time() * 1000)
    key_prefix: str = "slack:user-rate:"
    expire_seconds: int = 120
    fail_open: bool = False

    def __post_init__(self) -> None:
        if self.max_requests_per_minute <= 0:
            raise ValueError("max_requests_per_minute must be positive")
        if self.expire_seconds <= 0:
            raise ValueError("expire_seconds must be positive")

    async def try_acquire(self, tenant_id: str, user_id: str) -> bool:
        minute_key = self.now_millis() // 60_000
        key = f"{self.key_prefix}{rate_limit_identity(tenant_id, user_id)}:{minute_key}"
        try:
            count = await self.redis.eval(
                INCR_WITH_EXPIRE_SCRIPT,
                1,
                key,
                self.expire_seconds,
            )
        except Exception:
            return self.fail_open
        return _int_count(count) <= self.max_requests_per_minute

    async def close(self) -> None:
        close = getattr(self.redis, "aclose", None)
        if close is not None:
            await close()


def rate_limit_identity(tenant_id: str, user_id: str) -> str:
    tenant = tenant_id.strip() or "local"
    user = user_id.strip() or "unknown"
    return f"{tenant}:{user}"


def _int_count(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, bytes):
        return int(value.decode("utf-8"))
    if isinstance(value, str):
        return int(value)
    if isinstance(value, Sequence) and value:
        return _int_count(cast(object, value[0]))
    return 1


INCR_WITH_EXPIRE_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return count
""".strip()
