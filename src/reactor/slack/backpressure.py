from __future__ import annotations

import asyncio
from dataclasses import dataclass


@dataclass
class SlackBackpressureLimiter:
    max_concurrent_requests: int
    request_timeout_seconds: float
    fail_fast_on_saturation: bool

    def __post_init__(self) -> None:
        if self.max_concurrent_requests <= 0:
            raise ValueError("max_concurrent_requests must be positive")
        if self.request_timeout_seconds < 0:
            raise ValueError("request_timeout_seconds must not be negative")
        self._semaphore = asyncio.Semaphore(self.max_concurrent_requests)

    async def acquire(self) -> bool:
        if self.fail_fast_on_saturation:
            return self._acquire_nowait()
        if self.request_timeout_seconds <= 0:
            await self._semaphore.acquire()
            return True
        try:
            await asyncio.wait_for(
                self._semaphore.acquire(),
                timeout=self.request_timeout_seconds,
            )
        except TimeoutError:
            return False
        return True

    def release(self) -> None:
        self._semaphore.release()

    def _acquire_nowait(self) -> bool:
        if self._semaphore.locked():
            return False
        self._semaphore._value -= 1  # noqa: SLF001
        return True
