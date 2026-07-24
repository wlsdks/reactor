from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

import pytest

from reactor.hooks.runtime import run_fail_open_hooks


async def test_fail_open_hooks_continue_after_regular_exception() -> None:
    calls: list[str] = []

    async def failing_hook(state: Mapping[str, Any]) -> None:
        calls.append(f"fail:{state.get('run_id')}")
        raise RuntimeError("hook failed")

    async def succeeding_hook(state: Mapping[str, Any]) -> None:
        calls.append(f"ok:{state.get('run_id')}")

    failures = await run_fail_open_hooks(
        [failing_hook, succeeding_hook],
        {"run_id": "run_1"},
    )

    assert calls == ["fail:run_1", "ok:run_1"]
    assert [failure.as_metadata() for failure in failures] == [
        {"hook": "failing_hook", "error": "RuntimeError: hook failed"}
    ]


async def test_fail_open_hooks_rethrow_cancellation() -> None:
    async def cancelled_hook(_: Mapping[str, Any]) -> None:
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await run_fail_open_hooks([cancelled_hook], {"run_id": "run_1"})
