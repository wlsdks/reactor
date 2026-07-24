from __future__ import annotations

import json
from collections.abc import Mapping

from reactor.runs.lifecycle import (
    RUN_LIFECYCLE_CHANNEL,
    RedisRunLifecyclePublisher,
    publish_run_lifecycle_event,
)


class RecordingRedis:
    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []

    async def publish(self, channel: str, payload: str) -> int:
        self.published.append((channel, payload))
        return 1


class FailingPublisher:
    async def publish(self, event: Mapping[str, object]) -> bool:
        _ = event
        raise RuntimeError("pubsub unavailable")


async def test_redis_run_lifecycle_publisher_emits_json_pubsub_event() -> None:
    redis = RecordingRedis()
    publisher = RedisRunLifecyclePublisher(redis)

    accepted = await publisher.publish(
        {
            "event_type": "run.cancelled",
            "run_id": "run_123",
            "tenant_id": "tenant_1",
            "user_id": "user_1",
        }
    )

    assert accepted is True
    assert redis.published[0][0] == RUN_LIFECYCLE_CHANNEL
    assert json.loads(redis.published[0][1]) == {
        "event_type": "run.cancelled",
        "run_id": "run_123",
        "tenant_id": "tenant_1",
        "user_id": "user_1",
    }


async def test_publish_run_lifecycle_event_fails_open() -> None:
    await publish_run_lifecycle_event(
        FailingPublisher(),
        {"event_type": "approval.decided", "approval_id": "approval_1"},
    )
