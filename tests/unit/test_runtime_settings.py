from __future__ import annotations

from collections.abc import Sequence
from typing import cast

import pytest

from reactor.core.container import AppContainer
from reactor.core.runtime_settings import apply_runtime_settings_to_settings
from reactor.core.settings import Settings
from reactor.persistence.runtime_settings_store import SqlAlchemyRuntimeSettingsStore
from reactor.runtime_settings.service import (
    GLOBAL_TENANT_ID,
    RuntimeSettingRecord,
    RuntimeSettingsResolver,
)


class FakeRuntimeSettingsStore:
    def __init__(self, records: Sequence[RuntimeSettingRecord]) -> None:
        self._records = records

    async def list(self, *, tenant_id: str | None = None) -> Sequence[RuntimeSettingRecord]:
        if tenant_id is None:
            return self._records
        return [record for record in self._records if record.tenant_id == tenant_id]


class RuntimeSettingsAppContainer(AppContainer):
    _runtime_settings_store: FakeRuntimeSettingsStore

    def __init__(self, records: Sequence[RuntimeSettingRecord]) -> None:
        super().__init__(
            settings=Settings(max_tool_calls=1, response_cache_enabled=False),
            engine=None,
            session_factory=None,
            graph=object(),
            checkpointer=None,
        )
        object.__setattr__(self, "_runtime_settings_store", FakeRuntimeSettingsStore(records))

    def runtime_settings_store(self) -> SqlAlchemyRuntimeSettingsStore | None:
        return cast(SqlAlchemyRuntimeSettingsStore, self._runtime_settings_store)


def test_runtime_settings_resolver_prefers_tenant_override_then_global_default() -> None:
    resolver = RuntimeSettingsResolver(
        [
            RuntimeSettingRecord(
                tenant_id=GLOBAL_TENANT_ID,
                key="guard.rate_limit_per_minute",
                value="20",
                value_type="INT",
            ),
            RuntimeSettingRecord(
                tenant_id="tenant_1",
                key="guard.rate_limit_per_minute",
                value="7",
                value_type="INT",
            ),
        ]
    )

    assert resolver.get_int("guard.rate_limit_per_minute", 100, tenant_id="tenant_1") == 7
    assert resolver.get_int("guard.rate_limit_per_minute", 100, tenant_id="tenant_2") == 20


def test_runtime_settings_resolver_parses_boolean_and_falls_back_on_invalid_values() -> None:
    resolver = RuntimeSettingsResolver(
        [
            RuntimeSettingRecord(key="feature.a2a.enabled", value="yes", value_type="BOOLEAN"),
            RuntimeSettingRecord(key="feature.bad.enabled", value="maybe", value_type="BOOLEAN"),
        ]
    )

    assert resolver.get_boolean("feature.a2a.enabled", False) is True
    assert resolver.get_boolean("feature.bad.enabled", True) is True
    assert resolver.get_boolean("feature.missing.enabled", False) is False


def test_runtime_settings_resolver_parses_double_and_falls_back_on_invalid_values() -> None:
    resolver = RuntimeSettingsResolver(
        [
            RuntimeSettingRecord(key="llm.temperature", value="0.2", value_type="DOUBLE"),
            RuntimeSettingRecord(key="llm.bad_temperature", value="hot", value_type="DOUBLE"),
        ]
    )

    assert resolver.get_double("llm.temperature", 1.0) == 0.2
    assert resolver.get_double("llm.bad_temperature", 1.0) == 1.0


def test_runtime_setting_rejects_unsafe_keys_and_tenant_ids() -> None:
    with pytest.raises(ValueError, match="key must not contain whitespace"):
        RuntimeSettingRecord(key="guard bad", value="true").validate()

    with pytest.raises(ValueError, match="tenant_id must not contain whitespace"):
        RuntimeSettingRecord(tenant_id="tenant bad", key="guard.enabled", value="true").validate()


def test_apply_runtime_settings_to_settings_prefers_tenant_over_global() -> None:
    resolver = RuntimeSettingsResolver(
        [
            RuntimeSettingRecord(
                tenant_id=GLOBAL_TENANT_ID,
                key="settings.max_tool_calls",
                value="3",
                value_type="INT",
            ),
            RuntimeSettingRecord(
                tenant_id="tenant_1",
                key="settings.max_tool_calls",
                value="7",
                value_type="INT",
            ),
            RuntimeSettingRecord(
                tenant_id="tenant_1",
                key="settings.response_cache_enabled",
                value="true",
                value_type="BOOLEAN",
            ),
        ]
    )

    result = apply_runtime_settings_to_settings(
        Settings(max_tool_calls=1, response_cache_enabled=False),
        resolver,
        tenant_id="tenant_1",
    )

    assert result.settings.max_tool_calls == 7
    assert result.settings.response_cache_enabled is True
    assert result.applied_keys == (
        "settings.response_cache_enabled",
        "settings.max_tool_calls",
    )
    assert result.ignored_keys == ()
    assert result.errors == {}


def test_apply_runtime_settings_to_settings_parses_json_lists() -> None:
    resolver = RuntimeSettingsResolver(
        [
            RuntimeSettingRecord(
                key="settings.cors_allowed_origins",
                value='["https://app.example.com"]',
                value_type="JSON",
            )
        ]
    )

    result = apply_runtime_settings_to_settings(Settings(), resolver)

    assert result.settings.cors_allowed_origins == ["https://app.example.com"]
    assert result.applied_keys == ("settings.cors_allowed_origins",)


def test_apply_runtime_settings_to_settings_ignores_invalid_overrides() -> None:
    base = Settings(max_tool_calls=5)
    resolver = RuntimeSettingsResolver(
        [
            RuntimeSettingRecord(
                key="settings.max_tool_calls",
                value="200",
                value_type="INT",
            ),
            RuntimeSettingRecord(
                key="settings.response_cache_enabled",
                value="maybe",
                value_type="BOOLEAN",
            ),
        ]
    )

    result = apply_runtime_settings_to_settings(base, resolver)

    assert result.settings.max_tool_calls == 5
    assert result.settings.response_cache_enabled is False
    assert result.applied_keys == ()
    assert result.ignored_keys == (
        "settings.max_tool_calls",
        "settings.response_cache_enabled",
    )
    assert "less than or equal to 100" in result.errors["__settings__"]
    assert result.errors["settings.response_cache_enabled"] == (
        "invalid BOOLEAN value for settings.response_cache_enabled"
    )


async def test_app_container_effective_settings_merges_global_and_tenant_overrides() -> None:
    container = RuntimeSettingsAppContainer(
        [
            RuntimeSettingRecord(
                tenant_id=GLOBAL_TENANT_ID,
                key="settings.max_tool_calls",
                value="3",
                value_type="INT",
            ),
            RuntimeSettingRecord(
                tenant_id="tenant_1",
                key="settings.max_tool_calls",
                value="7",
                value_type="INT",
            ),
            RuntimeSettingRecord(
                tenant_id="tenant_1",
                key="settings.cors_allowed_origins",
                value='["https://tenant.example.com"]',
                value_type="JSON",
            ),
        ]
    )

    result = await container.effective_settings(tenant_id="tenant_1")

    assert result.settings.max_tool_calls == 7
    assert result.settings.cors_allowed_origins == ["https://tenant.example.com"]
    assert result.applied_keys == (
        "settings.max_tool_calls",
        "settings.cors_allowed_origins",
    )


async def test_app_container_effective_settings_returns_base_without_store() -> None:
    container = AppContainer.local(Settings(max_tool_calls=4))

    result = await container.effective_settings(tenant_id="tenant_1")

    assert result.settings.max_tool_calls == 4
    assert result.applied_keys == ()
