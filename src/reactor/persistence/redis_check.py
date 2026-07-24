from __future__ import annotations

from dataclasses import dataclass

from redis.asyncio import Redis


@dataclass(frozen=True)
class RedisHealth:
    configured: bool
    ok: bool
    detail: str


async def check_redis(redis_url: str | None, required: bool) -> RedisHealth:
    if not redis_url:
        return RedisHealth(
            configured=False,
            ok=not required,
            detail="redis not configured",
        )

    client = Redis.from_url(redis_url)
    try:
        await client.ping()
    except Exception as exc:
        return RedisHealth(
            configured=True,
            ok=not required,
            detail=f"redis unavailable: {exc.__class__.__name__}",
        )
    finally:
        await client.aclose()

    return RedisHealth(configured=True, ok=True, detail="ok")
