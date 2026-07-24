from __future__ import annotations

from collections.abc import Callable


def retry_langsmith_write(operation: Callable[[], object], *, max_attempts: int) -> None:
    attempts = max(1, max_attempts)
    for attempt in range(1, attempts + 1):
        try:
            operation()
            return
        except Exception:
            if attempt == attempts:
                raise
