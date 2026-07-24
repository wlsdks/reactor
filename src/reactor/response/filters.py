from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResponseFilterContext:
    tenant_id: str
    user_id: str
    tools_used: list[str]
    duration_ms: int
    verified_sources: list[str] = field(default_factory=lambda: [])
    tool_insights: list[str] = field(default_factory=lambda: [])


@runtime_checkable
class ResponseFilter(Protocol):
    @property
    def order(self) -> int: ...

    async def filter(self, content: str, context: ResponseFilterContext) -> str: ...


class ResponseFilterChain:
    def __init__(self, filters: Sequence[ResponseFilter]) -> None:
        self._filters = sorted(filters, key=lambda item: item.order)

    @property
    def size(self) -> int:
        return len(self._filters)

    async def apply(self, content: str, context: ResponseFilterContext) -> str:
        result = content
        for response_filter in self._filters:
            try:
                result = await response_filter.filter(result, context)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning(
                    "response filter failed open: %s",
                    response_filter.__class__.__name__,
                )
                continue
        return result


class MaxLengthResponseFilter:
    TRUNCATION_NOTICE = "\n\n[Response truncated]"

    def __init__(self, max_length: int = 0) -> None:
        self.max_length = max_length
        self.order = 10

    async def filter(self, content: str, context: ResponseFilterContext) -> str:
        del context
        if self.max_length <= 0 or len(content) <= self.max_length:
            return content
        return f"{content[: self.max_length]}{self.TRUNCATION_NOTICE}"


class SlackUserIdMaskResponseFilter:
    RAW_SLACK_USER_ID_PATTERN = re.compile(r"(?<![@\w])`?(U[A-Z0-9]{8,})`?(?![A-Za-z0-9])")

    @property
    def order(self) -> int:
        return 85

    async def filter(self, content: str, context: ResponseFilterContext) -> str:
        del context
        if not content.strip():
            return content
        return self.RAW_SLACK_USER_ID_PATTERN.sub(r"<@\1>", content)


class InternalBrandMaskResponseFilter:
    MULTI_SPACE_PATTERN = re.compile(r" {2,}")
    EXCESS_NEWLINE_PATTERN = re.compile(r"\n{3,}")
    PATTERNS: Sequence[tuple[re.Pattern[str], str]] = (
        (re.compile(r"\bLegacyOrg\s*/\s*reactor\b", re.IGNORECASE), "Reactor"),
        (re.compile(r"\bExample\s+Corp\b", re.IGNORECASE), "Reactor"),
        (re.compile(r"\bLegacyOrg\b", re.IGNORECASE), "Reactor"),
        (re.compile(r"\s+for\s+Reactor\s+internal\s+users\b", re.IGNORECASE), ""),
        (re.compile(r"\*\*?Reactor\s*\(\s*Reactor\s*\)\*\*?"), "*Reactor*"),
        (re.compile(r"Reactor\s*\(\s*Reactor\s*\)"), "Reactor"),
        (
            re.compile(
                r"(?m)^\s*[*\-•]\s*\*{0,2}(?:언어|프레임워크|Language|Framework)"
                r"[\s:]*\*{0,2}[^\n]*Kotlin[^\n]*$"
            ),
            "",
        ),
        (
            re.compile(
                r"(?m)^\s*[*\-•]\s*\*{0,2}(?:언어|프레임워크|Language|Framework)"
                r"[\s:]*\*{0,2}[^\n]*(?:Spring)[^\n]*$"
            ),
            "",
        ),
        (
            re.compile(
                r"\*{0,2}(?:Kotlin\s*/\s*Spring\s*Boot|Kotlin과\s*Spring\s*Boot)"
                r"(?:\s*기반(?:의|으로)?)?\*{0,2}"
            ),
            "",
        ),
        (
            re.compile(r"\*{0,2}(?:Spring\s*AI|Spring\s*Boot)(?:\s*기반(?:의|으로)?)?\*{0,2}\s*"),
            "",
        ),
        (
            re.compile(
                r"\*{0,2}(?:JVM\s*/\s*Gradle|Gradle\s*/\s*JVM)(?:\s*기반(?:의|으로)?)?\*{0,2}\s*"
            ),
            "",
        ),
        (re.compile(r",\s*,"), ","),
        (re.compile(r"\s+\."), "."),
    )

    @property
    def order(self) -> int:
        return 86

    async def filter(self, content: str, context: ResponseFilterContext) -> str:
        del context
        if not content.strip():
            return content
        result = content
        for pattern, replacement in self.PATTERNS:
            result = pattern.sub(replacement, result)
        result = self.MULTI_SPACE_PATTERN.sub(" ", result)
        result = self.EXCESS_NEWLINE_PATTERN.sub("\n\n", result)
        return result.rstrip()


def default_response_filter_chain() -> ResponseFilterChain:
    return ResponseFilterChain(
        [
            SlackUserIdMaskResponseFilter(),
            InternalBrandMaskResponseFilter(),
        ]
    )
