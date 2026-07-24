from __future__ import annotations

from datetime import UTC, datetime

from httpx import ASGITransport, AsyncClient

from reactor.admin.audit import AdminAuditAction, AdminAuditLog
from reactor.api.app import create_app
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


async def test_tool_policy_legacy_admin_flow_uses_runtime_settings() -> None:
    settings_store = FakeRuntimeSettingsStore()
    audit_store = FakeAdminAuditStore()
    app = create_app()
    app.state.reactor = FakeContainer(
        runtime_store=settings_store,
        audit_store=audit_store,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.get("/api/tool-policy", headers=USER_HEADERS)
        initial = await client.get("/api/tool-policy", headers=ADMIN_HEADERS)
        updated = await client.put(
            "/api/tool-policy",
            headers=ADMIN_HEADERS,
            json={
                "enabled": True,
                "writeToolNames": [" jira_create_issue ", "", "confluence_update_page"],
                "denyWriteChannels": ["Slack", "  "],
                "allowWriteToolNamesInDenyChannels": ["jira_add_comment"],
                "allowWriteToolNamesByChannel": {"Slack": ["jira_add_comment", " "]},
                "denyWriteMessage": "  blocked by policy  ",
            },
        )
        assert "tools.policy" in settings_store.records
        fetched = await client.get("/v1/tool-policy", headers=ADMIN_HEADERS)
        deleted = await client.delete("/api/tool-policy", headers=ADMIN_HEADERS)
        reset = await client.get("/api/tool-policy", headers=ADMIN_HEADERS)

    assert forbidden.status_code == 403
    assert initial.status_code == 200
    assert initial.json()["stored"] is None
    assert initial.json()["effective"]["enabled"] is False
    assert updated.status_code == 200
    assert updated.json()["writeToolNames"] == ["confluence_update_page", "jira_create_issue"]
    assert updated.json()["denyWriteChannels"] == ["slack"]
    assert updated.json()["allowWriteToolNamesByChannel"] == {"slack": ["jira_add_comment"]}
    assert updated.json()["denyWriteMessage"] == "blocked by policy"
    assert fetched.status_code == 200
    assert fetched.json()["stored"] == updated.json()
    assert fetched.json()["effective"] == updated.json()
    assert deleted.status_code == 204
    assert "tools.policy" not in settings_store.records
    assert reset.status_code == 200
    assert reset.json()["stored"] is None
    assert [entry.action for entry in audit_store.saved] == [
        AdminAuditAction.UPDATE,
        AdminAuditAction.DELETE,
    ]


class FakeContainer:
    def __init__(
        self,
        *,
        runtime_store: FakeRuntimeSettingsStore | None,
        audit_store: FakeAdminAuditStore,
    ) -> None:
        self._runtime_store = runtime_store
        self._audit_store = audit_store

    def runtime_settings_store(self) -> FakeRuntimeSettingsStore | None:
        return self._runtime_store

    def admin_audit_store(self) -> FakeAdminAuditStore:
        return self._audit_store

    def tool_store(self) -> None:
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
