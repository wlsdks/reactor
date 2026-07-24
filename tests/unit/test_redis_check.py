from __future__ import annotations

from reactor.core.settings import Settings
from reactor.persistence.redis_check import check_redis


async def test_optional_redis_can_be_unconfigured() -> None:
    health = await check_redis(None, required=False)

    assert health.configured is False
    assert health.ok is True
    assert health.detail == "redis not configured"


async def test_required_redis_fails_without_url() -> None:
    health = await check_redis(None, required=True)

    assert health.configured is False
    assert health.ok is False


def test_production_multi_replica_requires_redis_even_without_manual_flag() -> None:
    settings = Settings(
        environment="production",
        redis_required=False,
        api_replica_count=2,
        worker_replica_count=1,
    )

    assert settings.effective_redis_required() is True
