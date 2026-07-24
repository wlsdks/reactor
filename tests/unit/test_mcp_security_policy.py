from __future__ import annotations

from datetime import UTC, datetime

from reactor.core.settings import Settings
from reactor.mcp.security_policy import (
    MCP_SECURITY_POLICY_SETTING_KEY,
    config_default_policy,
    load_mcp_security_policy_state,
    normalize_allowed_server_names,
    save_mcp_security_policy,
)
from reactor.runtime_settings.service import RuntimeSettingRecord, RuntimeSettingUpdate


def test_config_default_policy_uses_settings_values() -> None:
    now = datetime(2026, 6, 27, tzinfo=UTC)
    policy = config_default_policy(
        Settings(
            mcp_security_allowed_server_names=["atlassian", " docs "],
            mcp_security_max_tool_output_length=120_000,
        ),
        now=now,
    )

    assert policy.allowed_server_names == frozenset({"atlassian", "docs"})
    assert policy.max_tool_output_length == 120_000
    assert policy.created_at == now


async def test_security_policy_state_prefers_stored_policy_over_config_default() -> None:
    store = FakeRuntimeSettingsStore()
    saved = await save_mcp_security_policy(
        store=store,
        allowed_server_names={"atlassian", "swagger-petstore"},
        max_tool_output_length=150_000,
        actor="admin_1",
    )

    effective, stored, config_default = await load_mcp_security_policy_state(
        settings=Settings(
            mcp_security_allowed_server_names=["atlassian"],
            mcp_security_max_tool_output_length=50_000,
        ),
        store=store,
    )

    assert stored == saved
    assert effective == saved
    assert config_default.allowed_server_names == frozenset({"atlassian"})
    assert store.records[MCP_SECURITY_POLICY_SETTING_KEY].updated_by == "admin_1"


def test_normalize_allowed_server_names_trims_blanks_and_deduplicates() -> None:
    assert normalize_allowed_server_names([" docs ", "", "docs", "jira"]) == frozenset(
        {"docs", "jira"}
    )


class FakeRuntimeSettingsStore:
    def __init__(self) -> None:
        self.records: dict[str, RuntimeSettingRecord] = {}

    async def find(
        self,
        key: str,
        *,
        tenant_id: str = "global",
    ) -> RuntimeSettingRecord | None:
        del tenant_id
        return self.records.get(key)

    async def set(self, update: RuntimeSettingUpdate) -> RuntimeSettingRecord:
        record = RuntimeSettingRecord(
            key=update.key,
            value=update.value,
            value_type=update.value_type,
            category=update.category,
            tenant_id=update.tenant_id,
            description=update.description,
            updated_by=update.updated_by,
            metadata=update.metadata,
            updated_at=datetime(2026, 6, 27, tzinfo=UTC),
        )
        self.records[record.key] = record
        return record

    async def delete(self, key: str, *, tenant_id: str = "global") -> None:
        del tenant_id
        self.records.pop(key, None)
