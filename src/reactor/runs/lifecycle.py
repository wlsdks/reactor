from __future__ import annotations

import json
from collections.abc import Mapping
from inspect import isawaitable
from typing import Any, Protocol, cast

RUN_LIFECYCLE_CHANNEL = "reactor:runs:lifecycle"


class RunLifecyclePublisher(Protocol):
    def publish(self, event: Mapping[str, object]) -> object: ...


class RedisRunLifecyclePublisher:
    def __init__(self, redis: Any, *, channel: str = RUN_LIFECYCLE_CHANNEL) -> None:
        self._redis = redis
        self._channel = channel

    async def publish(self, event: Mapping[str, object]) -> bool:
        payload = json.dumps(
            dict(event),
            default=str,
            separators=(",", ":"),
            sort_keys=True,
        )
        await self._redis.publish(self._channel, payload)
        return True

    async def close(self) -> None:
        close = getattr(self._redis, "aclose", None)
        if close is not None:
            await close()


async def publish_run_lifecycle_event(
    publisher: RunLifecyclePublisher | None,
    event: Mapping[str, object],
) -> None:
    if publisher is None:
        return
    try:
        result = publisher.publish(dict(event))
        if isawaitable(result):
            await cast(Any, result)
    except Exception:
        return
