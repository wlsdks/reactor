from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol, cast

from reactor.core.settings import Settings
from reactor.runtime_settings.service import (
    GLOBAL_TENANT_ID,
    RuntimeSettingRecord,
    RuntimeSettingUpdate,
)

MCP_SECURITY_POLICY_SETTING_KEY = "mcp.security.policy"
MCP_SECURITY_CATEGORY = "mcp_security"
MCP_SECURITY_DESCRIPTION = "Dynamic MCP server allowlist and tool output security policy."


@dataclass(frozen=True)
class McpSecurityPolicy:
    allowed_server_names: frozenset[str]
    max_tool_output_length: int
    created_at: datetime
    updated_at: datetime

    def validate(self) -> None:
        if len(self.allowed_server_names) > 500:
            raise ValueError("allowedServerNames must not exceed 500 entries")
        if self.max_tool_output_length < 1024:
            raise ValueError("maxToolOutputLength must be at least 1024")
        if self.max_tool_output_length > 500_000:
            raise ValueError("maxToolOutputLength must not exceed 500000")


class RuntimeSettingsStore(Protocol):
    async def find(
        self,
        key: str,
        *,
        tenant_id: str = GLOBAL_TENANT_ID,
    ) -> RuntimeSettingRecord | None: ...

    async def set(self, update: RuntimeSettingUpdate) -> RuntimeSettingRecord: ...

    async def delete(self, key: str, *, tenant_id: str = GLOBAL_TENANT_ID) -> None: ...


def config_default_policy(settings: Settings, *, now: datetime | None = None) -> McpSecurityPolicy:
    timestamp = now or datetime.now(UTC)
    return McpSecurityPolicy(
        allowed_server_names=normalize_allowed_server_names(
            settings.mcp_security_allowed_server_names
        ),
        max_tool_output_length=settings.mcp_security_max_tool_output_length,
        created_at=timestamp,
        updated_at=timestamp,
    )


def stored_policy_from_record(record: RuntimeSettingRecord | None) -> McpSecurityPolicy | None:
    if record is None:
        return None
    try:
        payload = json.loads(record.value)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    mapped_payload = cast(Mapping[str, Any], payload)
    allowed = mapped_payload.get("allowedServerNames", [])
    max_length = mapped_payload.get("maxToolOutputLength", 50_000)
    if isinstance(allowed, list):
        allowed_values: object = cast(list[object], allowed)
    else:
        allowed_values = ()
    policy = McpSecurityPolicy(
        allowed_server_names=normalize_allowed_server_names(allowed_values),
        max_tool_output_length=max_length if isinstance(max_length, int) else 50_000,
        created_at=record.updated_at,
        updated_at=record.updated_at,
    )
    policy.validate()
    return policy


async def load_mcp_security_policy_state(
    *,
    settings: Settings,
    store: RuntimeSettingsStore | None,
) -> tuple[McpSecurityPolicy, McpSecurityPolicy | None, McpSecurityPolicy]:
    config_default = config_default_policy(settings)
    stored = None
    if store is not None:
        stored = stored_policy_from_record(
            await store.find(MCP_SECURITY_POLICY_SETTING_KEY, tenant_id=GLOBAL_TENANT_ID)
        )
    effective = stored or config_default
    return effective, stored, config_default


async def save_mcp_security_policy(
    *,
    store: RuntimeSettingsStore,
    allowed_server_names: set[str],
    max_tool_output_length: int,
    actor: str,
) -> McpSecurityPolicy:
    now = datetime.now(UTC)
    policy = McpSecurityPolicy(
        allowed_server_names=normalize_allowed_server_names(allowed_server_names),
        max_tool_output_length=max_tool_output_length,
        created_at=now,
        updated_at=now,
    )
    policy.validate()
    record = await store.set(
        RuntimeSettingUpdate(
            key=MCP_SECURITY_POLICY_SETTING_KEY,
            value=json.dumps(
                {
                    "allowedServerNames": sorted(policy.allowed_server_names),
                    "maxToolOutputLength": policy.max_tool_output_length,
                },
                separators=(",", ":"),
            ),
            value_type="JSON",
            category=MCP_SECURITY_CATEGORY,
            tenant_id=GLOBAL_TENANT_ID,
            description=MCP_SECURITY_DESCRIPTION,
            updated_by=actor,
        )
    )
    return stored_policy_from_record(record) or policy


async def delete_mcp_security_policy(store: RuntimeSettingsStore) -> None:
    await store.delete(MCP_SECURITY_POLICY_SETTING_KEY, tenant_id=GLOBAL_TENANT_ID)


def normalize_allowed_server_names(values: object) -> frozenset[str]:
    if not isinstance(values, (list, set, tuple, frozenset)):
        return frozenset()
    iterable = cast(Iterable[object], values)
    normalized = {str(value).strip() for value in iterable if str(value).strip()}
    return frozenset(normalized)


def epoch_millis(value: datetime) -> int:
    return int(value.timestamp() * 1000)
