from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol, cast

from reactor.core.settings import Settings
from reactor.runtime_settings.service import (
    GLOBAL_TENANT_ID,
    RuntimeSettingRecord,
    RuntimeSettingUpdate,
)

RAG_INGESTION_POLICY_SETTING_KEY = "rag.ingestion.policy"


class RuntimeSettingsStore(Protocol):
    async def set(self, update: RuntimeSettingUpdate) -> RuntimeSettingRecord: ...

    async def find(
        self,
        key: str,
        *,
        tenant_id: str = GLOBAL_TENANT_ID,
    ) -> RuntimeSettingRecord | None: ...

    async def delete(
        self,
        key: str,
        *,
        tenant_id: str = GLOBAL_TENANT_ID,
    ) -> None: ...


@dataclass(frozen=True)
class RagIngestionPolicy:
    enabled: bool
    require_review: bool
    allowed_channels: tuple[str, ...] = ()
    min_query_chars: int = 10
    min_response_chars: int = 20
    blocked_patterns: tuple[str, ...] = ()
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def from_settings(cls, settings: Settings) -> RagIngestionPolicy:
        return normalize_policy(
            cls(
                enabled=settings.rag_ingestion_enabled,
                require_review=settings.rag_ingestion_require_review,
                allowed_channels=tuple(settings.rag_ingestion_allowed_channels),
                min_query_chars=settings.rag_ingestion_min_query_chars,
                min_response_chars=settings.rag_ingestion_min_response_chars,
                blocked_patterns=tuple(settings.rag_ingestion_blocked_patterns),
            )
        )


class RagIngestionPolicyProvider:
    def __init__(self, settings: Settings, store: RagIngestionPolicyStore) -> None:
        self._settings = settings
        self._store = store
        self._cached: RagIngestionPolicy | None = None
        self._cached_at: datetime | None = None

    def invalidate(self) -> None:
        self._cached = None
        self._cached_at = None

    async def current(self) -> RagIngestionPolicy:
        if not self._settings.rag_ingestion_enabled:
            return RagIngestionPolicy(
                enabled=False,
                require_review=self._settings.rag_ingestion_require_review,
                min_query_chars=max(1, self._settings.rag_ingestion_min_query_chars),
                min_response_chars=max(1, self._settings.rag_ingestion_min_response_chars),
                created_at=datetime.fromtimestamp(0, UTC),
                updated_at=datetime.fromtimestamp(0, UTC),
            )
        if not self._settings.rag_ingestion_dynamic_enabled:
            return RagIngestionPolicy.from_settings(self._settings)

        now = datetime.now(UTC)
        refresh_ms = max(250, self._settings.rag_ingestion_dynamic_refresh_ms)
        if (
            self._cached is not None
            and self._cached_at is not None
            and (now - self._cached_at).total_seconds() * 1000 < refresh_ms
        ):
            return self._cached
        try:
            policy = await self._store.get_or_none()
        except Exception:
            policy = None
        resolved = policy or RagIngestionPolicy.from_settings(self._settings)
        self._cached = normalize_policy(resolved)
        self._cached_at = now
        return self._cached


class RagIngestionPolicyStore:
    def __init__(self, runtime_settings_store: RuntimeSettingsStore) -> None:
        self._runtime_settings_store = runtime_settings_store

    async def get_or_none(self) -> RagIngestionPolicy | None:
        record = await self._runtime_settings_store.find(RAG_INGESTION_POLICY_SETTING_KEY)
        if record is None:
            return None
        return policy_from_setting(record)

    async def save(
        self,
        policy: RagIngestionPolicy,
        *,
        actor: str | None = None,
    ) -> RagIngestionPolicy:
        normalized = normalize_policy(policy)
        record = await self._runtime_settings_store.set(
            RuntimeSettingUpdate(
                key=RAG_INGESTION_POLICY_SETTING_KEY,
                value=json.dumps(policy_to_payload(normalized), ensure_ascii=False),
                value_type="JSON",
                category="rag",
                description="Dynamic RAG ingestion capture policy",
                updated_by=actor,
                metadata={"owner": "rag_ingestion_policy"},
            )
        )
        loaded = policy_from_setting(record)
        return loaded if loaded is not None else normalized

    async def delete(self) -> None:
        await self._runtime_settings_store.delete(RAG_INGESTION_POLICY_SETTING_KEY)


def normalize_policy(policy: RagIngestionPolicy) -> RagIngestionPolicy:
    return RagIngestionPolicy(
        enabled=policy.enabled,
        require_review=policy.require_review,
        allowed_channels=normalize_string_set(policy.allowed_channels, lowercase=True),
        min_query_chars=max(1, policy.min_query_chars),
        min_response_chars=max(1, policy.min_response_chars),
        blocked_patterns=normalize_string_set(policy.blocked_patterns, lowercase=False),
        created_at=policy.created_at,
        updated_at=policy.updated_at,
    )


def normalize_string_set(values: Iterable[str], *, lowercase: bool) -> tuple[str, ...]:
    normalized: set[str] = set()
    for value in values:
        item = value.strip()
        if not item:
            continue
        normalized.add(item.lower() if lowercase else item)
    return tuple(sorted(normalized))


def policy_to_payload(policy: RagIngestionPolicy) -> dict[str, Any]:
    return {
        "enabled": policy.enabled,
        "requireReview": policy.require_review,
        "allowedChannels": list(policy.allowed_channels),
        "minQueryChars": policy.min_query_chars,
        "minResponseChars": policy.min_response_chars,
        "blockedPatterns": list(policy.blocked_patterns),
        "createdAt": policy.created_at.isoformat(),
        "updatedAt": policy.updated_at.isoformat(),
    }


def policy_from_setting(record: RuntimeSettingRecord) -> RagIngestionPolicy | None:
    try:
        payload = json.loads(record.value)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    data = cast(dict[str, object], payload)
    created_at = parse_datetime(data.get("createdAt")) or record.updated_at
    updated_at = record.updated_at
    return normalize_policy(
        RagIngestionPolicy(
            enabled=bool(data.get("enabled", False)),
            require_review=bool(data.get("requireReview", True)),
            allowed_channels=string_tuple(data.get("allowedChannels")),
            min_query_chars=int_value(data.get("minQueryChars"), default=10),
            min_response_chars=int_value(data.get("minResponseChars"), default=20),
            blocked_patterns=string_tuple(data.get("blockedPatterns")),
            created_at=created_at,
            updated_at=updated_at,
        )
    )


def parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def string_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(str(item) for item in cast(list[object], value))
    if isinstance(value, tuple):
        return tuple(str(item) for item in cast(tuple[object, ...], value))
    if isinstance(value, set):
        return tuple(str(item) for item in cast(set[object], value))
    return ()


def int_value(value: object, *, default: int) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float | str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def epoch_millis(value: datetime) -> int:
    return int(value.timestamp() * 1000)
