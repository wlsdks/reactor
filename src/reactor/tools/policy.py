from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol, cast

from reactor.runtime_settings.service import RuntimeSettingRecord, RuntimeSettingUpdate

TOOL_POLICY_SETTING_KEY = "tools.policy"
DEFAULT_DENY_WRITE_MESSAGE = "Error: This tool is not allowed in this channel"


class ToolPolicySettingsStore(Protocol):
    async def find(
        self,
        key: str,
        *,
        tenant_id: str = "global",
    ) -> RuntimeSettingRecord | None: ...

    async def set(self, update: RuntimeSettingUpdate) -> RuntimeSettingRecord: ...

    async def delete(self, key: str, *, tenant_id: str = "global") -> None: ...


@dataclass(frozen=True)
class DynamicToolPolicy:
    enabled: bool = False
    write_tool_names: tuple[str, ...] = ()
    deny_write_channels: tuple[str, ...] = ()
    allow_write_tool_names_in_deny_channels: tuple[str, ...] = ()
    allow_write_tool_names_by_channel: Mapping[str, tuple[str, ...]] = field(
        default_factory=lambda: {}
    )
    deny_write_message: str = DEFAULT_DENY_WRITE_MESSAGE
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class ToolPolicyState:
    config_enabled: bool
    dynamic_enabled: bool
    effective: DynamicToolPolicy
    stored: DynamicToolPolicy | None


def default_tool_policy() -> DynamicToolPolicy:
    return DynamicToolPolicy()


async def load_tool_policy_state(
    store: ToolPolicySettingsStore | None,
    *,
    tenant_id: str,
) -> ToolPolicyState:
    stored = await load_stored_tool_policy(store, tenant_id=tenant_id)
    return ToolPolicyState(
        config_enabled=default_tool_policy().enabled,
        dynamic_enabled=store is not None,
        effective=stored or default_tool_policy(),
        stored=stored,
    )


async def save_tool_policy(
    store: ToolPolicySettingsStore,
    *,
    tenant_id: str,
    enabled: bool,
    write_tool_names: Iterable[str],
    deny_write_channels: Iterable[str],
    allow_write_tool_names_in_deny_channels: Iterable[str],
    allow_write_tool_names_by_channel: Mapping[str, Iterable[str]],
    deny_write_message: str,
    actor: str,
) -> DynamicToolPolicy:
    existing = await load_stored_tool_policy(store, tenant_id=tenant_id)
    now = datetime.now(UTC)
    policy = DynamicToolPolicy(
        enabled=enabled,
        write_tool_names=normalize_values(write_tool_names),
        deny_write_channels=normalize_values(deny_write_channels, lowercase=True),
        allow_write_tool_names_in_deny_channels=normalize_values(
            allow_write_tool_names_in_deny_channels
        ),
        allow_write_tool_names_by_channel=normalize_mapping(
            allow_write_tool_names_by_channel,
            lowercase_keys=True,
        ),
        deny_write_message=deny_write_message.strip() or DEFAULT_DENY_WRITE_MESSAGE,
        created_at=existing.created_at if existing is not None else now,
        updated_at=now,
    )
    await store.set(
        RuntimeSettingUpdate(
            key=TOOL_POLICY_SETTING_KEY,
            value=tool_policy_to_json(policy),
            value_type="JSON",
            category="tools",
            tenant_id=tenant_id,
            description="Dynamic tool execution policy",
            updated_by=actor,
        )
    )
    return policy


async def delete_tool_policy(store: ToolPolicySettingsStore, *, tenant_id: str) -> None:
    await store.delete(TOOL_POLICY_SETTING_KEY, tenant_id=tenant_id)


async def load_stored_tool_policy(
    store: ToolPolicySettingsStore | None,
    *,
    tenant_id: str,
) -> DynamicToolPolicy | None:
    if store is None:
        return None
    record = await store.find(TOOL_POLICY_SETTING_KEY, tenant_id=tenant_id)
    if record is None:
        return None
    return tool_policy_from_json(record.value)


def tool_policy_to_json(policy: DynamicToolPolicy) -> str:
    return json.dumps(tool_policy_payload(policy), separators=(",", ":"), sort_keys=True)


def tool_policy_from_json(raw: str) -> DynamicToolPolicy:
    payload = cast(object, json.loads(raw))
    if not isinstance(payload, dict):
        raise ValueError("tool policy payload must be an object")
    typed_payload = cast(dict[str, object], payload)
    created_at = parse_datetime(typed_payload.get("createdAt")) or datetime.now(UTC)
    updated_at = parse_datetime(typed_payload.get("updatedAt")) or created_at
    return DynamicToolPolicy(
        enabled=bool(typed_payload.get("enabled", False)),
        write_tool_names=normalize_values(read_iterable(typed_payload.get("writeToolNames"))),
        deny_write_channels=normalize_values(
            read_iterable(typed_payload.get("denyWriteChannels")), lowercase=True
        ),
        allow_write_tool_names_in_deny_channels=normalize_values(
            read_iterable(typed_payload.get("allowWriteToolNamesInDenyChannels"))
        ),
        allow_write_tool_names_by_channel=normalize_mapping(
            read_mapping(typed_payload.get("allowWriteToolNamesByChannel")),
            lowercase_keys=True,
        ),
        deny_write_message=str(typed_payload.get("denyWriteMessage") or DEFAULT_DENY_WRITE_MESSAGE),
        created_at=created_at,
        updated_at=updated_at,
    )


def tool_policy_payload(policy: DynamicToolPolicy) -> dict[str, Any]:
    return {
        "enabled": policy.enabled,
        "writeToolNames": list(policy.write_tool_names),
        "denyWriteChannels": list(policy.deny_write_channels),
        "allowWriteToolNamesInDenyChannels": list(policy.allow_write_tool_names_in_deny_channels),
        "allowWriteToolNamesByChannel": {
            key: list(value)
            for key, value in sorted(policy.allow_write_tool_names_by_channel.items())
        },
        "denyWriteMessage": policy.deny_write_message,
        "createdAt": policy.created_at.isoformat(),
        "updatedAt": policy.updated_at.isoformat(),
    }


def normalize_values(values: Iterable[object], *, lowercase: bool = False) -> tuple[str, ...]:
    normalized: set[str] = set()
    for value in values:
        item = str(value).strip()
        if not item:
            continue
        normalized.add(item.lower() if lowercase else item)
    return tuple(sorted(normalized))


def normalize_mapping(
    values_by_key: Mapping[str, Iterable[object]],
    *,
    lowercase_keys: bool = False,
) -> dict[str, tuple[str, ...]]:
    normalized: dict[str, tuple[str, ...]] = {}
    for raw_key, values in values_by_key.items():
        key = raw_key.strip()
        if lowercase_keys:
            key = key.lower()
        if not key:
            continue
        normalized_values = normalize_values(values)
        if normalized_values:
            normalized[key] = normalized_values
    return dict(sorted(normalized.items()))


def read_iterable(value: object) -> Iterable[object]:
    if isinstance(value, list | tuple | set):
        return tuple(cast(Iterable[object], value))
    return ()


def read_mapping(value: object) -> Mapping[str, Iterable[object]]:
    if not isinstance(value, dict):
        return {}
    typed_value = cast(dict[object, object], value)
    return {str(key): read_iterable(raw_value) for key, raw_value in typed_value.items()}


def parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
