from __future__ import annotations

from reactor.persistence.runtime_settings_store import (
    build_runtime_setting_delete,
    build_runtime_setting_find,
    build_runtime_setting_list,
    build_runtime_setting_upsert,
)
from reactor.runtime_settings.service import RuntimeSettingUpdate


def test_runtime_setting_upsert_uses_tenant_key_conflict_constraint() -> None:
    statement = build_runtime_setting_upsert(
        RuntimeSettingUpdate(
            tenant_id="tenant_1",
            key="guard.rate_limit_per_minute",
            value="30",
            value_type="INT",
            category="guard",
            description="Per-minute guard limit",
            updated_by="admin_1",
            metadata={"source": "admin_api"},
        )
    )
    compiled = statement.compile()
    sql = str(compiled)

    assert "runtime_settings" in sql
    assert "ON CONFLICT ON CONSTRAINT uq_runtime_settings_key DO UPDATE" in sql
    assert compiled.params["tenant_id"] == "tenant_1"
    assert compiled.params["key"] == "guard.rate_limit_per_minute"
    assert compiled.params["value"] == "30"
    assert compiled.params["type"] == "INT"
    assert compiled.params["metadata"] == {"source": "admin_api"}


def test_runtime_setting_find_filters_tenant_and_key() -> None:
    compiled = build_runtime_setting_find(
        "feature.a2a.enabled",
        tenant_id="tenant_1",
    ).compile()
    sql = str(compiled)

    assert "runtime_settings.tenant_id =" in sql
    assert "runtime_settings.key =" in sql
    assert compiled.params["tenant_id_1"] == "tenant_1"
    assert compiled.params["key_1"] == "feature.a2a.enabled"


def test_runtime_setting_list_can_scope_to_tenant() -> None:
    compiled = build_runtime_setting_list(tenant_id="tenant_1").compile()
    sql = str(compiled)

    assert "runtime_settings.tenant_id =" in sql
    assert "ORDER BY runtime_settings.tenant_id ASC" in sql
    assert compiled.params["tenant_id_1"] == "tenant_1"


def test_runtime_setting_delete_scopes_to_tenant_and_key() -> None:
    compiled = build_runtime_setting_delete(
        "guard.rate_limit_per_minute",
        tenant_id="tenant_1",
    ).compile()
    sql = str(compiled)

    assert "DELETE FROM runtime_settings" in sql
    assert "runtime_settings.tenant_id =" in sql
    assert "runtime_settings.key =" in sql
    assert compiled.params["tenant_id_1"] == "tenant_1"
    assert compiled.params["key_1"] == "guard.rate_limit_per_minute"
