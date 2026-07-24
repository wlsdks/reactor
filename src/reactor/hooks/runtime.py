from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

ReactorHook = Callable[[Mapping[str, Any]], Awaitable[None]]


@dataclass(frozen=True)
class HookFailure:
    hook: str
    error: str

    def as_metadata(self) -> dict[str, str]:
        return {"hook": self.hook, "error": self.error}


async def run_fail_open_hooks(
    hooks: Sequence[ReactorHook],
    state: Mapping[str, Any],
) -> list[HookFailure]:
    failures: list[HookFailure] = []
    for hook in hooks:
        try:
            await hook(state)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            failures.append(
                HookFailure(
                    hook=hook_name(hook),
                    error=f"{error.__class__.__name__}: {error}",
                )
            )
    return failures


def hook_name(hook: ReactorHook) -> str:
    return getattr(hook, "__name__", hook.__class__.__name__)
