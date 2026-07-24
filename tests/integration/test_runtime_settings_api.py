from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from hashlib import sha256

from httpx import ASGITransport, AsyncClient

from reactor.api.app import create_app
from reactor.core.runtime_settings import apply_runtime_settings_to_settings
from reactor.core.settings import Settings
from reactor.runtime_settings.service import (
    GLOBAL_TENANT_ID,
    RuntimeSettingRecord,
    RuntimeSettingsResolver,
    RuntimeSettingUpdate,
)
from reactor.tools.catalog import ToolSpec

ADMIN_HEADERS = {
    "X-Reactor-Admin": "true",
    "X-Reactor-User-Id": "admin_1",
    "X-Reactor-Tenant-Id": "tenant_1",
}


async def test_runtime_settings_api_requires_admin_header() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/v1/admin/settings")

    assert response.status_code == 403
    assert response.json()["detail"] == "permission required: settings:read"


async def test_runtime_settings_api_rejects_admin_manager_without_settings_permission() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/v1/admin/settings",
            headers={"X-Reactor-Role": "ADMIN_MANAGER", "X-Reactor-User-Id": "manager_1"},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "permission required: settings:read"


async def test_runtime_settings_api_rejects_invalid_api_key_before_header_admin_fallback() -> None:
    valid_api_key = "reactor-valid-api-key"  # noqa: S105
    app = create_app()
    app.state.reactor = FakeContainer(
        FakeRuntimeSettingsStore(),
        settings=Settings(
            auth_api_keys=[
                (f"key_1:tenant_1:service_admin:ADMIN:{sha256(valid_api_key.encode()).hexdigest()}")
            ]
        ),
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/v1/admin/settings",
            headers={
                "X-Reactor-API-Key": "invalid-api-key",
                "X-Reactor-Admin": "true",
                "X-Reactor-User-Id": "spoofed_admin",
            },
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "invalid API key"


async def test_runtime_settings_api_requires_persistence_after_auth() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/v1/admin/settings", headers=ADMIN_HEADERS)

    assert response.status_code == 503
    assert response.json()["detail"] == "runtime settings persistence is not configured"


async def test_runtime_settings_legacy_path_is_kept_for_migration_parity() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/api/admin/settings/refresh", headers=ADMIN_HEADERS)

    assert response.status_code == 200
    assert response.json() == {"status": "cache_refreshed"}


async def test_runtime_settings_api_set_get_list_and_delete_with_store() -> None:
    app = create_app()
    store = FakeRuntimeSettingsStore()
    app.state.reactor = FakeContainer(store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        set_response = await client.put(
            "/v1/admin/settings/guard.rate_limit_per_minute",
            params={"tenant_id": "tenant_2"},
            headers=ADMIN_HEADERS,
            json={
                "value": "30",
                "type": "INT",
                "category": "guard",
                "description": "Per-minute guard limit",
                "metadata": {"source": "test"},
            },
        )
        get_response = await client.get(
            "/v1/admin/settings/guard.rate_limit_per_minute",
            params={"tenant_id": "tenant_2"},
            headers=ADMIN_HEADERS,
        )
        list_response = await client.get(
            "/v1/admin/settings",
            params={"tenant_id": "tenant_2"},
            headers=ADMIN_HEADERS,
        )
        delete_response = await client.delete(
            "/v1/admin/settings/guard.rate_limit_per_minute",
            params={"tenant_id": "tenant_2"},
            headers=ADMIN_HEADERS,
        )

    assert set_response.status_code == 200
    assert set_response.json() == {
        "tenantId": "tenant_1",
        "key": "guard.rate_limit_per_minute",
        "value": "30",
        "status": "updated",
    }
    assert get_response.status_code == 200
    assert get_response.json()["updatedBy"] == "admin_1"
    assert list_response.status_code == 200
    assert list_response.json()[0]["metadata"] == {"source": "test"}
    assert delete_response.status_code == 204
    assert store.deleted == ("tenant_1", "guard.rate_limit_per_minute")


async def test_runtime_settings_langchain_middleware_policy_endpoint_reports_effective_policy() -> (
    None
):
    app = create_app()
    store = FakeRuntimeSettingsStore()
    await store.set(
        RuntimeSettingUpdate(
            tenant_id=GLOBAL_TENANT_ID,
            key="langchain.middleware_policy",
            value=json.dumps({"toolCallRunLimit": 8}),
            value_type="JSON",
            category="langchain",
            updated_by="admin_1",
        )
    )
    await store.set(
        RuntimeSettingUpdate(
            tenant_id="tenant_1",
            key="langchain.middleware_policy",
            value=json.dumps(
                {
                    "modelCallRunLimit": 5,
                    "toolCallRunLimit": 3,
                    "modelRetryMaxRetries": 0,
                    "toolRetryMaxRetries": 2,
                    "piiRules": [
                        {
                            "type": "email",
                            "strategy": "block",
                            "applyToInput": False,
                            "applyToOutput": False,
                            "applyToToolResults": True,
                        }
                    ],
                }
            ),
            value_type="JSON",
            category="langchain",
            updated_by="admin_1",
        )
    )
    app.state.reactor = FakeContainer(store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/v1/admin/settings/langchain/middleware-policy",
            headers=ADMIN_HEADERS,
        )

    assert response.status_code == 200
    assert response.json() == {
        "tenantId": "tenant_1",
        "key": "langchain.middleware_policy",
        "status": "applied",
        "source": "tenant_runtime_setting",
        "settingTenantId": "tenant_1",
        "reason": None,
        "policy": {
            "modelCallRunLimit": 5,
            "toolCallRunLimit": 3,
            "modelRetryMaxRetries": 0,
            "toolRetryMaxRetries": 2,
            "piiRules": [
                {
                    "type": "email",
                    "strategy": "block",
                    "applyToInput": False,
                    "applyToOutput": False,
                    "applyToToolResults": True,
                    "applyToStreamOutput": False,
                }
            ],
        },
        "middlewareChain": {
            "status": "applied",
            "count": 5,
            "middleware": [
                "ModelCallLimitMiddleware",
                "ToolCallLimitMiddleware",
                "ModelRetryMiddleware",
                "ToolRetryMiddleware",
                "PIIMiddleware",
            ],
            "piiRuleCount": 1,
            "hitlToolCount": 0,
            "fallbackModelCount": 0,
        },
    }


async def test_runtime_settings_langchain_middleware_policy_endpoint_reports_default_policy() -> (
    None
):
    app = create_app()
    store = FakeRuntimeSettingsStore()
    app.state.reactor = FakeContainer(store, settings=Settings(max_tool_calls=6))
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/v1/admin/settings/langchain/middleware-policy",
            headers=ADMIN_HEADERS,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["tenantId"] == "tenant_1"
    assert body["key"] == "langchain.middleware_policy"
    assert body["status"] == "default"
    assert body["source"] == "default"
    assert body["settingTenantId"] is None
    assert body["reason"] is None
    assert body["policy"]["modelCallRunLimit"] == 7
    assert body["policy"]["toolCallRunLimit"] == 6
    assert body["policy"]["piiRules"][0] == {
        "type": "email",
        "strategy": "redact",
        "applyToInput": True,
        "applyToOutput": True,
        "applyToToolResults": True,
        "applyToStreamOutput": True,
    }
    assert body["middlewareChain"] == {
        "status": "applied",
        "count": 9,
        "middleware": [
            "ModelCallLimitMiddleware",
            "ToolCallLimitMiddleware",
            "ModelRetryMiddleware",
            "ToolRetryMiddleware",
            "PIIMiddleware",
            "PIIMiddleware",
            "PIIMiddleware",
            "PIIMiddleware",
            "PIIMiddleware",
        ],
        "piiRuleCount": 5,
        "hitlToolCount": 0,
        "fallbackModelCount": 0,
    }


async def test_runtime_settings_langchain_middleware_policy_preview_reports_chain() -> None:
    app = create_app()
    store = FakeRuntimeSettingsStore()
    app.state.reactor = FakeContainer(store, settings=Settings(max_tool_calls=6))
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/admin/settings/langchain/middleware-policy/preview",
            headers=ADMIN_HEADERS,
            json={
                "policy": {
                    "modelCallRunLimit": 5,
                    "toolCallRunLimit": 3,
                    "modelRetryMaxRetries": 0,
                    "toolRetryMaxRetries": 2,
                    "piiRules": [
                        {
                            "type": "email",
                            "strategy": "block",
                            "applyToInput": False,
                            "applyToOutput": False,
                            "applyToToolResults": True,
                        }
                    ],
                },
                "interruptOnTools": ["DangerousServer:delete_file"],
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "tenantId": "tenant_1",
        "key": "langchain.middleware_policy",
        "status": "preview",
        "source": "request",
        "reason": None,
        "policy": {
            "modelCallRunLimit": 5,
            "toolCallRunLimit": 3,
            "modelRetryMaxRetries": 0,
            "toolRetryMaxRetries": 2,
            "piiRules": [
                {
                    "type": "email",
                    "strategy": "block",
                    "applyToInput": False,
                    "applyToOutput": False,
                    "applyToToolResults": True,
                    "applyToStreamOutput": False,
                }
            ],
        },
        "middlewareChain": {
            "status": "applied",
            "count": 6,
            "middleware": [
                "ModelCallLimitMiddleware",
                "ToolCallLimitMiddleware",
                "ModelRetryMiddleware",
                "ToolRetryMiddleware",
                "PIIMiddleware",
                "HumanInTheLoopMiddleware",
            ],
            "piiRuleCount": 1,
            "hitlToolCount": 1,
            "fallbackModelCount": 0,
        },
    }


async def test_runtime_settings_langchain_middleware_policy_preview_rejects_invalid_policy() -> (
    None
):
    app = create_app()
    store = FakeRuntimeSettingsStore()
    app.state.reactor = FakeContainer(store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/admin/settings/langchain/middleware-policy/preview",
            headers=ADMIN_HEADERS,
            json={"policy": {"toolCallRunLimit": -1}},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "invalid langchain.middleware_policy"


async def test_runtime_settings_api_rejects_invalid_langchain_middleware_policy_update() -> None:
    app = create_app()
    store = FakeRuntimeSettingsStore()
    app.state.reactor = FakeContainer(store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.put(
            "/v1/admin/settings/langchain.middleware_policy",
            headers=ADMIN_HEADERS,
            json={
                "value": json.dumps({"toolCallRunLimit": -1}),
                "type": "JSON",
                "category": "langchain",
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "invalid langchain.middleware_policy"
    assert store.records == {}


async def test_runtime_settings_api_rejects_empty_langchain_pii_rules() -> None:
    app = create_app()
    store = FakeRuntimeSettingsStore()
    app.state.reactor = FakeContainer(store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.put(
            "/v1/admin/settings/langchain.middleware_policy",
            headers=ADMIN_HEADERS,
            json={
                "value": json.dumps({"toolCallRunLimit": 3, "piiRules": []}),
                "type": "JSON",
                "category": "langchain",
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "invalid langchain.middleware_policy"
    assert store.records == {}


async def test_runtime_settings_api_rejects_independent_stream_output_pii_scope() -> None:
    app = create_app()
    store = FakeRuntimeSettingsStore()
    app.state.reactor = FakeContainer(store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.put(
            "/v1/admin/settings/langchain.middleware_policy",
            headers=ADMIN_HEADERS,
            json={
                "value": json.dumps(
                    {
                        "piiRules": [
                            {
                                "type": "email",
                                "strategy": "redact",
                                "applyToOutput": True,
                                "applyToStreamOutput": False,
                            }
                        ]
                    }
                ),
                "type": "JSON",
                "category": "langchain",
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "invalid langchain.middleware_policy"
    assert store.records == {}


async def test_runtime_settings_tool_profile_budget_endpoint_reports_effective_budget() -> None:
    app = create_app()
    store = FakeRuntimeSettingsStore()
    await store.set(
        RuntimeSettingUpdate(
            tenant_id=GLOBAL_TENANT_ID,
            key="tools.profile_budget",
            value=json.dumps({"maxTools": 8}),
            value_type="JSON",
            category="tools",
            updated_by="admin_1",
        )
    )
    await store.set(
        RuntimeSettingUpdate(
            tenant_id="tenant_1",
            key="tools.profile_budget",
            value=json.dumps(
                {
                    "maxTools": 3,
                    "allowedRiskLevels": ["read", "write"],
                    "allowedTools": ["Rag:hybrid_search", "Docs:lookup"],
                    "deniedTools": ["Slack:post_message"],
                }
            ),
            value_type="JSON",
            category="tools",
            updated_by="admin_1",
        )
    )
    app.state.reactor = FakeContainer(
        store,
        tools=[
            fake_tool_spec("Rag", "hybrid_search", "read"),
            fake_tool_spec("Docs", "lookup", "read"),
            fake_tool_spec("Slack", "post_message", "write"),
        ],
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/v1/admin/settings/tools/profile-budget",
            headers=ADMIN_HEADERS,
        )

    assert response.status_code == 200
    assert response.json() == {
        "tenantId": "tenant_1",
        "key": "tools.profile_budget",
        "status": "applied",
        "source": "tenant_runtime_setting",
        "settingTenantId": "tenant_1",
        "reason": None,
        "budget": {
            "maxTools": 3,
            "allowedRiskLevels": ["read", "write"],
            "allowedTools": ["Docs:lookup", "Rag:hybrid_search"],
            "deniedTools": ["Slack:post_message"],
        },
        "configuredToolCount": 3,
        "activeToolCount": 2,
        "activeTools": ["Rag:hybrid_search", "Docs:lookup"],
        "droppedToolCount": 1,
        "droppedTools": [
            {
                "tool": "Slack:post_message",
                "riskLevel": "write",
                "reason": "denied_tool",
            }
        ],
    }


async def test_runtime_settings_tool_profile_budget_preview_reports_active_and_dropped_tools() -> (
    None
):
    app = create_app()
    store = FakeRuntimeSettingsStore()
    app.state.reactor = FakeContainer(store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/admin/settings/tools/profile-budget/preview",
            headers=ADMIN_HEADERS,
            json={
                "budget": {
                    "maxTools": 1,
                    "allowedRiskLevels": ["read"],
                    "deniedTools": ["Slack:post_message"],
                },
                "configuredTools": [
                    {"name": "Rag:hybrid_search", "riskLevel": "read"},
                    {"name": "Docs:lookup", "riskLevel": "read"},
                    {"name": "Slack:post_message", "riskLevel": "write"},
                ],
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "tenantId": "tenant_1",
        "key": "tools.profile_budget",
        "status": "preview",
        "source": "request",
        "reason": None,
        "budget": {
            "maxTools": 1,
            "allowedRiskLevels": ["read"],
            "allowedTools": None,
            "deniedTools": ["Slack:post_message"],
        },
        "configuredToolCount": 3,
        "activeToolCount": 1,
        "activeTools": ["Rag:hybrid_search"],
        "droppedToolCount": 2,
        "droppedTools": [
            {
                "tool": "Slack:post_message",
                "riskLevel": "write",
                "reason": "denied_tool",
            },
            {
                "tool": "Docs:lookup",
                "riskLevel": "read",
                "reason": "max_tools_exceeded",
            },
        ],
    }


async def test_runtime_settings_tool_profile_budget_preview_rejects_invalid_budget() -> None:
    app = create_app()
    store = FakeRuntimeSettingsStore()
    app.state.reactor = FakeContainer(store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/admin/settings/tools/profile-budget/preview",
            headers=ADMIN_HEADERS,
            json={
                "budget": {"maxTools": -1},
                "configuredTools": [{"name": "Rag:hybrid_search", "riskLevel": "read"}],
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "invalid tools.profile_budget"


async def test_runtime_settings_api_rejects_invalid_tool_profile_budget_update() -> None:
    app = create_app()
    store = FakeRuntimeSettingsStore()
    app.state.reactor = FakeContainer(store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.put(
            "/v1/admin/settings/tools.profile_budget",
            headers=ADMIN_HEADERS,
            json={
                "value": json.dumps({"maxTools": -1}),
                "type": "JSON",
                "category": "tools",
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "invalid tools.profile_budget"
    assert store.records == {}


async def test_runtime_settings_api_rejects_non_string_tool_profile_budget_lists() -> None:
    app = create_app()
    store = FakeRuntimeSettingsStore()
    app.state.reactor = FakeContainer(store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.put(
            "/v1/admin/settings/tools.profile_budget",
            headers=ADMIN_HEADERS,
            json={
                "value": json.dumps({"allowedRiskLevels": ["read", True]}),
                "type": "JSON",
                "category": "tools",
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "invalid tools.profile_budget"
    assert store.records == {}


async def test_runtime_settings_effective_endpoint_reports_invalid_overrides() -> None:
    app = create_app()
    store = FakeRuntimeSettingsStore()
    await store.set(
        RuntimeSettingUpdate(
            tenant_id=GLOBAL_TENANT_ID,
            key="settings.max_tool_calls",
            value="200",
            value_type="INT",
            category="settings",
            updated_by="admin_1",
        )
    )
    await store.set(
        RuntimeSettingUpdate(
            tenant_id=GLOBAL_TENANT_ID,
            key="settings.response_cache_enabled",
            value="maybe",
            value_type="BOOLEAN",
            category="settings",
            updated_by="admin_1",
        )
    )
    app.state.reactor = FakeContainer(store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/v1/admin/settings/effective", headers=ADMIN_HEADERS)

    assert response.status_code == 200
    assert response.json()["tenantId"] == "global"
    assert response.json()["appliedKeys"] == []
    assert response.json()["ignoredKeys"] == [
        "settings.max_tool_calls",
        "settings.response_cache_enabled",
    ]
    assert "less than or equal to 100" in response.json()["errors"]["__settings__"]
    assert response.json()["errors"]["settings.response_cache_enabled"] == (
        "invalid BOOLEAN value for settings.response_cache_enabled"
    )


class FakeContainer:
    def __init__(
        self,
        store: FakeRuntimeSettingsStore,
        *,
        settings: Settings | None = None,
        tools: Sequence[ToolSpec] | None = None,
    ) -> None:
        self._store = store
        self._tools = list(tools or [])
        self.settings = settings or Settings(max_tool_calls=4, response_cache_enabled=False)

    def runtime_settings_store(self) -> FakeRuntimeSettingsStore:
        return self._store

    def tool_store(self) -> FakeToolStore:
        return FakeToolStore(self._tools)

    async def effective_settings(self, *, tenant_id: str = GLOBAL_TENANT_ID):
        records = list(await self._store.list(tenant_id=tenant_id))
        if tenant_id != GLOBAL_TENANT_ID:
            records = [*await self._store.list(tenant_id=GLOBAL_TENANT_ID), *records]
        return apply_runtime_settings_to_settings(
            self.settings,
            RuntimeSettingsResolver(records),
            tenant_id=tenant_id,
        )


class FakeToolStore:
    def __init__(self, tools: Sequence[ToolSpec]) -> None:
        self._tools = list(tools)

    async def list_enabled_tool_specs(self, tenant_id: str) -> Sequence[ToolSpec]:
        return [tool for tool in self._tools if tool.tenant_id == tenant_id and tool.enabled]


def fake_tool_spec(namespace: str, name: str, risk_level: str) -> ToolSpec:
    return ToolSpec(
        tenant_id="tenant_1",
        namespace=namespace,
        name=name,
        description=f"{namespace} {name}",
        risk_level=risk_level,
        input_schema={"type": "object", "properties": {}},
        output_schema={"type": "object", "properties": {}},
    )


class FakeRuntimeSettingsStore:
    def __init__(self) -> None:
        self.records: dict[tuple[str, str], RuntimeSettingRecord] = {}
        self.deleted: tuple[str, str] | None = None

    async def set(self, update: RuntimeSettingUpdate) -> RuntimeSettingRecord:
        record = RuntimeSettingRecord(
            tenant_id=update.tenant_id,
            key=update.key,
            value=update.value,
            value_type=update.value_type,
            category=update.category,
            description=update.description,
            updated_by=update.updated_by,
            updated_at=datetime(2026, 6, 26, tzinfo=UTC),
            metadata=update.metadata,
        )
        self.records[(record.tenant_id, record.key)] = record
        return record

    async def find(self, key: str, *, tenant_id: str) -> RuntimeSettingRecord | None:
        return self.records.get((tenant_id, key))

    async def list(self, *, tenant_id: str | None = None) -> Sequence[RuntimeSettingRecord]:
        records = list(self.records.values())
        if tenant_id is not None:
            records = [record for record in records if record.tenant_id == tenant_id]
        return records

    async def delete(self, key: str, *, tenant_id: str) -> None:
        self.deleted = (tenant_id, key)
        self.records.pop((tenant_id, key), None)
