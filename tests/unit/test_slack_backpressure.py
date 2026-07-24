from __future__ import annotations

from reactor.slack.backpressure import SlackBackpressureLimiter


async def test_slack_backpressure_limiter_rejects_when_fail_fast_saturated() -> None:
    limiter = SlackBackpressureLimiter(
        max_concurrent_requests=1,
        request_timeout_seconds=0,
        fail_fast_on_saturation=True,
    )

    first = await limiter.acquire()
    second = await limiter.acquire()

    assert first is True
    assert second is False

    limiter.release()

    assert await limiter.acquire() is True


async def test_slack_backpressure_limiter_times_out_in_queue_mode() -> None:
    limiter = SlackBackpressureLimiter(
        max_concurrent_requests=1,
        request_timeout_seconds=0.01,
        fail_fast_on_saturation=False,
    )

    assert await limiter.acquire() is True
    assert await limiter.acquire() is False
