from __future__ import annotations

from dataclasses import dataclass

from httpx import ASGITransport, AsyncClient

from reactor.admin.audit import AdminAuditAction, AdminAuditLog
from reactor.api.app import create_app
from reactor.mcp.registry import McpServerRegistration
from reactor.persistence.mcp_store import McpAccessPolicyRecord

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


async def test_mcp_access_policy_legacy_management_flow() -> None:
    mcp_store = FakeMcpRegistryStore(
        {
            "docs": McpServerRecord(
                id="mcp_1",
                tenant_id="tenant_1",
                name="docs",
            )
        }
    )
    audit_store = FakeAdminAuditStore()
    app = create_app()
    app.state.reactor = FakeContainer(mcp_store=mcp_store, audit_store=audit_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.get("/api/mcp/servers/docs/access-policy", headers=USER_HEADERS)
        missing = await client.get("/api/mcp/servers/missing/access-policy", headers=ADMIN_HEADERS)
        updated = await client.put(
            "/api/mcp/servers/docs/access-policy",
            headers=ADMIN_HEADERS,
            json={
                "graphProfile": "default",
                "allowWrite": True,
                "allowedTools": ["docs:search", "docs:fetch"],
            },
        )
        listed = await client.get("/v1/mcp/servers/docs/access-policy", headers=ADMIN_HEADERS)
        emergency = await client.post(
            "/api/mcp/servers/docs/access-policy/emergency-deny-all",
            headers=ADMIN_HEADERS,
        )
        deleted = await client.delete("/api/mcp/servers/docs/access-policy", headers=ADMIN_HEADERS)
        cleared = await client.get("/api/mcp/servers/docs/access-policy", headers=ADMIN_HEADERS)

    assert forbidden.status_code == 403
    assert missing.status_code == 404
    assert updated.status_code == 200
    updated_policy = updated.json()["policies"][0]
    assert updated_policy["id"].startswith("mcp_policy_")
    assert [
        {key: value for key, value in policy.items() if key != "id"}
        for policy in updated.json()["policies"]
    ] == [
        {
            "serverId": "mcp_1",
            "graphProfile": "default",
            "allowWrite": True,
            "allowedTools": ["docs:search", "docs:fetch"],
        }
    ]
    assert listed.status_code == 200
    assert listed.json()["policies"][0]["allowWrite"] is True
    assert emergency.status_code == 200
    assert emergency.json()["policies"][0]["allowWrite"] is False
    assert emergency.json()["policies"][0]["allowedTools"] == []
    assert deleted.status_code == 204
    assert cleared.status_code == 200
    assert cleared.json()["policies"] == []
    assert [entry.action for entry in audit_store.saved] == [
        AdminAuditAction.READ,
        AdminAuditAction.UPDATE,
        AdminAuditAction.READ,
        AdminAuditAction.UPDATE,
        AdminAuditAction.DELETE,
        AdminAuditAction.READ,
    ]


class FakeContainer:
    def __init__(
        self,
        *,
        mcp_store: FakeMcpRegistryStore,
        audit_store: FakeAdminAuditStore,
    ) -> None:
        self._mcp_store = mcp_store
        self._audit_store = audit_store

    def mcp_registry_store(self) -> FakeMcpRegistryStore:
        return self._mcp_store

    def admin_audit_store(self) -> FakeAdminAuditStore:
        return self._audit_store


@dataclass(frozen=True)
class McpServerRecord:
    id: str
    tenant_id: str
    name: str


class FakeMcpRegistryStore:
    def __init__(self, servers: dict[str, McpServerRecord]) -> None:
        self.servers = dict(servers)
        self.policies: dict[tuple[str, str], McpAccessPolicyRecord] = {}

    async def register_server(self, registration: McpServerRegistration) -> str:
        record = McpServerRecord(
            id=f"mcp_{len(self.servers) + 1}",
            tenant_id=registration.tenant_id,
            name=registration.name,
        )
        self.servers[record.name] = record
        return record.id

    async def list_servers(self, tenant_id: str) -> list[McpServerRecord]:
        return [server for server in self.servers.values() if server.tenant_id == tenant_id]

    async def find_server_by_name(self, *, tenant_id: str, name: str) -> McpServerRecord | None:
        server = self.servers.get(name)
        if server is None or server.tenant_id != tenant_id:
            return None
        return server

    async def list_access_policies(
        self,
        *,
        tenant_id: str,
        server_id: str,
    ) -> list[McpAccessPolicyRecord]:
        return [
            record
            for record in self.policies.values()
            if record.tenant_id == tenant_id and record.server_id == server_id
        ]

    async def save_access_policy(self, record: McpAccessPolicyRecord) -> McpAccessPolicyRecord:
        self.policies[(record.server_id, record.graph_profile)] = record
        return record

    async def delete_access_policies(self, *, tenant_id: str, server_id: str) -> int:
        keys = [
            key
            for key, record in self.policies.items()
            if record.tenant_id == tenant_id and record.server_id == server_id
        ]
        for key in keys:
            self.policies.pop(key, None)
        return len(keys)


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
