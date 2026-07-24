from __future__ import annotations

from datetime import UTC, datetime

from httpx import ASGITransport, AsyncClient

from reactor.admin.audit import AdminAuditAction, AdminAuditLog
from reactor.api.app import create_app
from reactor.core.settings import Settings
from reactor.runtime_settings.service import RuntimeSettingRecord, RuntimeSettingUpdate

ADMIN_HEADERS = {
    "X-Reactor-User-Id": "admin_1",
    "X-Reactor-Tenant-Id": "tenant_1",
    "X-Reactor-Role": "ADMIN",
}
USER_HEADERS = {
    "X-Reactor-User-Id": "user_1",
    "X-Reactor-Tenant-Id": "tenant_1",
    "X-Reactor-Role": "USER",
}


async def test_mcp_security_get_exposes_effective_stored_and_config_default() -> None:
    runtime_store = FakeRuntimeSettingsStore()
    audit_store = FakeAdminAuditStore()
    app = create_app()
    app.state.reactor = FakeContainer(
        runtime_store=runtime_store,
        audit_store=audit_store,
        settings=Settings(
            mcp_security_allowed_server_names=["atlassian"],
            mcp_security_max_tool_output_length=50_000,
        ),
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/mcp/security", headers=ADMIN_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["effective"]["allowedServerNames"] == ["atlassian"]
    assert body["effective"]["maxToolOutputLength"] == 50_000
    assert body["stored"] is None
    assert body["configDefault"]["allowedServerNames"] == ["atlassian"]


async def test_mcp_security_update_persists_policy_and_records_audit() -> None:
    runtime_store = FakeRuntimeSettingsStore()
    audit_store = FakeAdminAuditStore()
    app = create_app()
    app.state.reactor = FakeContainer(runtime_store=runtime_store, audit_store=audit_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.put(
            "/api/mcp/security",
            headers=USER_HEADERS,
            json={"allowedServerNames": ["docs"], "maxToolOutputLength": 120_000},
        )
        response = await client.put(
            "/v1/mcp/security",
            headers=ADMIN_HEADERS,
            json={
                "allowedServerNames": [" docs ", "", "jira", "docs"],
                "maxToolOutputLength": 120_000,
            },
        )

    assert forbidden.status_code == 403
    assert response.status_code == 200
    assert response.json()["allowedServerNames"] == ["docs", "jira"]
    assert response.json()["maxToolOutputLength"] == 120_000
    assert runtime_store.records["mcp.security.policy"].value == (
        '{"allowedServerNames":["docs","jira"],"maxToolOutputLength":120000}'
    )
    assert audit_store.saved[0].category == "mcp_security"
    assert audit_store.saved[0].action == AdminAuditAction.UPDATE
    assert audit_store.saved[0].detail == "allowedServers=2, maxToolOutputLength=120000"


async def test_mcp_security_delete_resets_to_config_defaults() -> None:
    runtime_store = FakeRuntimeSettingsStore()
    audit_store = FakeAdminAuditStore()
    app = create_app()
    app.state.reactor = FakeContainer(runtime_store=runtime_store, audit_store=audit_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        await client.put(
            "/api/mcp/security",
            headers=ADMIN_HEADERS,
            json={"allowedServerNames": ["docs"], "maxToolOutputLength": 120_000},
        )
        response = await client.request("DELETE", "/api/mcp/security", headers=ADMIN_HEADERS)

    assert response.status_code == 204
    assert "mcp.security.policy" not in runtime_store.records
    assert audit_store.saved[-1].action == AdminAuditAction.DELETE
    assert audit_store.saved[-1].detail == "reset_to_config_defaults=true"


async def test_mcp_security_update_requires_runtime_settings_persistence() -> None:
    app = create_app()
    app.state.reactor = FakeContainer(runtime_store=None, audit_store=FakeAdminAuditStore())
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        get_response = await client.get("/api/mcp/security", headers=ADMIN_HEADERS)
        update_response = await client.put(
            "/api/mcp/security",
            headers=ADMIN_HEADERS,
            json={"allowedServerNames": ["docs"], "maxToolOutputLength": 120_000},
        )

    assert get_response.status_code == 200
    assert update_response.status_code == 503
    assert update_response.json()["detail"] == "runtime settings persistence is not configured"


class FakeContainer:
    def __init__(
        self,
        *,
        runtime_store: FakeRuntimeSettingsStore | None,
        audit_store: FakeAdminAuditStore,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self._runtime_store = runtime_store
        self._audit_store = audit_store

    def runtime_settings_store(self) -> FakeRuntimeSettingsStore | None:
        return self._runtime_store

    def admin_audit_store(self) -> FakeAdminAuditStore:
        return self._audit_store

    def mcp_registry_store(self) -> None:
        return None


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
            updated_at=datetime(2026, 6, 27, tzinfo=UTC),
            metadata=dict(update.metadata),
        )
        self.records[record.key] = record
        return record

    async def delete(self, key: str, *, tenant_id: str = "global") -> None:
        del tenant_id
        self.records.pop(key, None)


class FakeAdminAuditStore:
    def __init__(self) -> None:
        self.saved: list[AdminAuditLog] = []

    async def save(
        self,
        record: AdminAuditLog,
        *,
        tenant_id: str,
    ) -> AdminAuditLog:
        del tenant_id
        self.saved.append(record)
        return record
