from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol


class OutputMinViolationMode(StrEnum):
    WARN = "WARN"
    RETRY_ONCE = "RETRY_ONCE"
    FAIL = "FAIL"


@dataclass(frozen=True)
class OutputBoundarySettings:
    output_max_chars: int = 0
    output_min_chars: int = 0
    output_min_violation_mode: OutputMinViolationMode = OutputMinViolationMode.WARN


@dataclass(frozen=True)
class OutputBoundaryViolation:
    violation_type: str
    policy: str
    limit: int
    actual: int
    metadata: Mapping[str, object] = field(default_factory=lambda: {})


class OutputBoundaryViolationRecorder(Protocol):
    def record(self, violation: OutputBoundaryViolation) -> None: ...


class NoopOutputBoundaryViolationRecorder:
    def record(self, violation: OutputBoundaryViolation) -> None:
        del violation


AttemptLongerResponse = Callable[[str, int], str | Awaitable[str | None] | None]


class OutputBoundaryEnforcer:
    VIOLATION_OUTPUT_TOO_SHORT = "output_too_short"
    VIOLATION_OUTPUT_TOO_LONG = "output_too_long"
    TRUNCATION_SUFFIX = "\n\n[Response truncated]"

    def __init__(
        self,
        *,
        settings: OutputBoundarySettings,
        violation_recorder: OutputBoundaryViolationRecorder | None = None,
    ) -> None:
        self._settings = settings
        self._violation_recorder = violation_recorder or NoopOutputBoundaryViolationRecorder()

    async def enforce(
        self,
        content: str,
        *,
        metadata: Mapping[str, object],
        attempt_longer_response: AttemptLongerResponse | None = None,
    ) -> str | None:
        result = self._truncate_if_needed(content, metadata=metadata)
        effective_length = self._effective_length_after_truncation(
            original=content,
            current=result,
        )
        if (
            self._settings.output_min_chars <= 0
            or effective_length >= self._settings.output_min_chars
        ):
            return result
        return await self._handle_min_violation(
            result,
            actual=effective_length,
            metadata=metadata,
            attempt_longer_response=attempt_longer_response,
        )

    def _truncate_if_needed(
        self,
        content: str,
        *,
        metadata: Mapping[str, object],
    ) -> str:
        max_chars = self._settings.output_max_chars
        if max_chars <= 0 or len(content) <= max_chars:
            return content
        self._record(
            violation_type=self.VIOLATION_OUTPUT_TOO_LONG,
            policy="truncate",
            limit=max_chars,
            actual=len(content),
            metadata=metadata,
        )
        return f"{content[:max_chars]}{self.TRUNCATION_SUFFIX}"

    async def _handle_min_violation(
        self,
        content: str,
        *,
        actual: int,
        metadata: Mapping[str, object],
        attempt_longer_response: AttemptLongerResponse | None,
    ) -> str | None:
        mode = self._settings.output_min_violation_mode
        self._record(
            violation_type=self.VIOLATION_OUTPUT_TOO_SHORT,
            policy=mode.value.lower(),
            limit=self._settings.output_min_chars,
            actual=actual,
            metadata=metadata,
        )
        if mode == OutputMinViolationMode.WARN:
            return content
        if mode == OutputMinViolationMode.FAIL:
            return None
        if attempt_longer_response is None:
            return content
        retry_result = attempt_longer_response(content, self._settings.output_min_chars)
        if asyncio.iscoroutine(retry_result) or isinstance(retry_result, Awaitable):
            retry_result = await retry_result
        if isinstance(retry_result, str) and len(retry_result) >= self._settings.output_min_chars:
            return retry_result
        return content

    def _effective_length_after_truncation(self, *, original: str, current: str) -> int:
        if current != original and self._settings.output_max_chars > 0:
            return self._settings.output_max_chars
        return len(current)

    def _record(
        self,
        *,
        violation_type: str,
        policy: str,
        limit: int,
        actual: int,
        metadata: Mapping[str, object],
    ) -> None:
        self._violation_recorder.record(
            OutputBoundaryViolation(
                violation_type=violation_type,
                policy=policy,
                limit=limit,
                actual=actual,
                metadata=metadata,
            )
        )
