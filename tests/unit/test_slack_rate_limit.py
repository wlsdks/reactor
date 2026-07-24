from __future__ import annotations

from reactor.slack.rate_limit import InMemorySlackUserRateLimiter, RedisSlackUserRateLimiter


def test_slack_user_rate_limiter_limits_each_user_independently() -> None:
    now = 1000.0
    limiter = InMemorySlackUserRateLimiter(
        max_requests_per_window=2,
        window_seconds=60,
        now=lambda: now,
    )

    assert limiter.try_acquire("tenant_1", "U1") is True
    assert limiter.try_acquire("tenant_1", "U1") is True
    assert limiter.try_acquire("tenant_1", "U1") is False
    assert limiter.try_acquire("tenant_1", "U2") is True
    assert limiter.try_acquire("tenant_2", "U1") is True

    now += 61

    assert limiter.try_acquire("tenant_1", "U1") is True


async def test_redis_slack_user_rate_limiter_uses_tenant_scoped_atomic_counter_with_ttl() -> None:
    redis = RecordingRedisClient(results=[1, 2, 3])
    limiter = RedisSlackUserRateLimiter(
        redis=redis,
        max_requests_per_minute=2,
        now_millis=lambda: 1782500061000,
    )

    assert await limiter.try_acquire("tenant_1", "U1") is True
    assert await limiter.try_acquire("tenant_1", "U1") is True
    assert await limiter.try_acquire("tenant_1", "U1") is False
    assert redis.calls == [
        ("slack:user-rate:tenant_1:U1:29708334", 120),
        ("slack:user-rate:tenant_1:U1:29708334", 120),
        ("slack:user-rate:tenant_1:U1:29708334", 120),
    ]


async def test_redis_slack_user_rate_limiter_keeps_tenants_independent() -> None:
    redis = RecordingRedisClient(results=[1, 1])
    limiter = RedisSlackUserRateLimiter(
        redis=redis,
        max_requests_per_minute=1,
        now_millis=lambda: 1782500061000,
    )

    assert await limiter.try_acquire("tenant_a", "U1") is True
    assert await limiter.try_acquire("tenant_b", "U1") is True
    assert [call[0] for call in redis.calls] == [
        "slack:user-rate:tenant_a:U1:29708334",
        "slack:user-rate:tenant_b:U1:29708334",
    ]


async def test_redis_slack_user_rate_limiter_fails_closed_on_redis_error_by_default() -> None:
    limiter = RedisSlackUserRateLimiter(
        redis=RaisingRedisClient(),
        max_requests_per_minute=1,
        now_millis=lambda: 1782500061000,
    )

    assert await limiter.try_acquire("tenant_1", "U1") is False


async def test_redis_slack_user_rate_limiter_can_fail_open_when_configured() -> None:
    limiter = RedisSlackUserRateLimiter(
        redis=RaisingRedisClient(),
        max_requests_per_minute=1,
        now_millis=lambda: 1782500061000,
        fail_open=True,
    )

    assert await limiter.try_acquire("tenant_1", "U1") is True


class RecordingRedisClient:
    def __init__(self, *, results: list[int]) -> None:
        self._results = list(results)
        self.calls: list[tuple[str, int]] = []

    async def eval(
        self,
        script: str,
        numkeys: int,
        *keys_and_args: object,
    ) -> int:
        assert "INCR" in script
        assert numkeys == 1
        key = str(keys_and_args[0])
        raw_expire_seconds = keys_and_args[1]
        assert isinstance(raw_expire_seconds, int)
        expire_seconds = raw_expire_seconds
        self.calls.append((key, expire_seconds))
        return self._results.pop(0)


class RaisingRedisClient:
    async def eval(
        self,
        script: str,
        numkeys: int,
        *keys_and_args: object,
    ) -> int:
        del script, numkeys, keys_and_args
        raise TimeoutError("redis unavailable")
