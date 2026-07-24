from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from time import monotonic
from typing import Protocol


@dataclass(frozen=True)
class IntentDefinition:
    name: str
    description: str
    examples: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    profile: str = "default"
    enabled: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("name is required")
        if not self.description.strip():
            raise ValueError("description is required")
        if not self.profile.strip():
            raise ValueError("profile is required")

    def with_updates(
        self,
        *,
        description: str | None = None,
        examples: tuple[str, ...] | None = None,
        keywords: tuple[str, ...] | None = None,
        profile: str | None = None,
        enabled: bool | None = None,
    ) -> IntentDefinition:
        return replace(
            self,
            description=self.description if description is None else description,
            examples=self.examples if examples is None else examples,
            keywords=self.keywords if keywords is None else keywords,
            profile=self.profile if profile is None else profile,
            enabled=self.enabled if enabled is None else enabled,
            updated_at=datetime.now(UTC),
        )


class IntentRegistry(Protocol):
    async def list(self) -> list[IntentDefinition]: ...

    async def get(self, intent_name: str) -> IntentDefinition | None: ...

    async def save(self, intent: IntentDefinition) -> IntentDefinition: ...

    async def delete(self, intent_name: str) -> None: ...


class InMemoryIntentRegistry:
    def __init__(self) -> None:
        self._intents: dict[str, IntentDefinition] = {}

    async def list(self) -> list[IntentDefinition]:
        return sorted(self._intents.values(), key=lambda intent: intent.name)

    async def get(self, intent_name: str) -> IntentDefinition | None:
        return self._intents.get(intent_name)

    async def save(self, intent: IntentDefinition) -> IntentDefinition:
        intent.validate()
        self._intents[intent.name] = intent
        return intent

    async def delete(self, intent_name: str) -> None:
        self._intents.pop(intent_name, None)


@dataclass(frozen=True)
class ResolvedIntent:
    intent_name: str
    profile: str
    confidence: float
    classified_by: str
    matched_keywords: tuple[str, ...] = ()
    latency_ms: int = 0


class RuleBasedIntentResolver:
    def __init__(
        self,
        registry: IntentRegistry,
        *,
        confidence_threshold: float = 0.6,
    ) -> None:
        self._registry = registry
        self._confidence_threshold = confidence_threshold

    async def resolve(self, text: str) -> ResolvedIntent | None:
        started = monotonic()
        normalized = text.casefold()
        matches: list[ResolvedIntent] = []
        for intent in await self._registry.list():
            if not intent.enabled or not intent.keywords:
                continue
            matched = tuple(
                keyword
                for keyword in intent.keywords
                if keyword.strip() and keyword.casefold() in normalized
            )
            if not matched:
                continue
            confidence = min(1.0, len(matched) / len(intent.keywords))
            if confidence < self._confidence_threshold:
                continue
            matches.append(
                ResolvedIntent(
                    intent_name=intent.name,
                    profile=intent.profile,
                    confidence=confidence,
                    classified_by="rule",
                    matched_keywords=matched,
                    latency_ms=int((monotonic() - started) * 1000),
                )
            )
        return max(matches, key=lambda match: match.confidence) if matches else None
