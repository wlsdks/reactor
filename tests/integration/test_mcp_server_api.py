from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from httpx import ASGITransport, AsyncClient

from reactor.api.app import create_app
from reactor.mcp.registry import McpServerRegistration

ADMIN_HEADERS = {
    "X-Reactor-User-Id": "admin_1",
    "X-Reactor-Tenant-Id": "tenant_1",
    "X-Reactor-Role": "ADMIN",
}


async def test_mcp_server_legacy_detail_update_delete_and_connection_flow() -> None:
    store = FakeMcpRegistryStore(
        {
            "docs": McpServerRecord(
                id="mcp_1",
                tenant_id="tenant_1",
                name="docs",
                transport="streamable_http",
                status="registered",
                command=None,
                url="https://mcp.example.com/mcp",
                auth_type="bearer",
                timeout_ms=15_000,
                reconnect_policy={"adminToken": "secret"},
            )
        }
    )
    app = create_app()
    app.state.reactor = FakeContainer(store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        detail = await client.get("/api/mcp/servers/docs", headers=ADMIN_HEADERS)
        updated = await client.put(
            "/api/mcp/servers/docs",
            headers=ADMIN_HEADERS,
            json={
                "transport": "streamable_http",
                "url": "https://mcp.example.com/v2/mcp",
                "authType": "none",
                "timeoutMs": 30000,
                "reconnectPolicy": {"maxAttempts": 2},
            },
        )
        assert store.servers["docs"].timeout_ms == 30_000
        connected = await client.post("/api/mcp/servers/docs/connect", headers=ADMIN_HEADERS)
        disconnected = await client.post("/v1/mcp/servers/docs/disconnect", headers=ADMIN_HEADERS)
        deleted = await client.delete("/api/mcp/servers/docs", headers=ADMIN_HEADERS)
        missing = await client.get("/api/mcp/servers/docs", headers=ADMIN_HEADERS)

    assert detail.status_code == 200
    assert detail.json()["name"] == "docs"
    assert updated.status_code == 200
    assert updated.json()["url"] == "https://mcp.example.com/v2/mcp"
    assert connected.status_code == 200
    assert connected.json()["status"] == "healthy"
    assert disconnected.status_code == 200
    assert disconnected.json()["status"] == "disabled"
    assert deleted.status_code == 204
    assert missing.status_code == 404


async def test_mcp_server_register_and_list_scope_to_principal_tenant() -> None:
    store = FakeMcpRegistryStore(
        {
            "other": McpServerRecord(
                id="mcp_other",
                tenant_id="tenant_2",
                name="other",
                transport="streamable_http",
                status="registered",
                command=None,
                url="https://other.example.com/mcp",
                auth_type="none",
                timeout_ms=15_000,
                reconnect_policy={},
            )
        }
    )
    app = create_app()
    app.state.reactor = FakeContainer(store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        unauthenticated = await client.get("/v1/mcp/servers", params={"tenant_id": "tenant_1"})
        registered = await client.post(
            "/api/mcp/servers",
            headers=ADMIN_HEADERS,
            json={
                "tenant_id": "tenant_2",
                "name": "docs",
                "transport": "streamable_http",
                "url": "https://mcp.example.com/mcp",
                "auth_type": "none",
            },
        )
        listed = await client.get(
            "/v1/mcp/servers",
            headers=ADMIN_HEADERS,
        )

    assert unauthenticated.status_code == 403
    assert registered.status_code == 201
    assert registered.json()["tenant_id"] == "tenant_1"
    assert listed.status_code == 200
    assert [server["name"] for server in listed.json()] == ["docs"]
    assert [server["tenant_id"] for server in listed.json()] == ["tenant_1"]


class FakeContainer:
    def __init__(self, mcp_store: FakeMcpRegistryStore) -> None:
        self._mcp_store = mcp_store

    def mcp_registry_store(self) -> FakeMcpRegistryStore:
        return self._mcp_store


@dataclass(frozen=True)
class McpServerRecord:
    id: str
    tenant_id: str
    name: str
    transport: str
    status: str
    command: str | None
    url: str | None
    auth_type: str
    timeout_ms: int
    reconnect_policy: dict[str, Any]


class FakeMcpRegistryStore:
    def __init__(self, servers: dict[str, McpServerRecord]) -> None:
        self.servers = dict(servers)

    async def register_server(self, registration: McpServerRegistration) -> str:
        record = McpServerRecord(
            id=f"mcp_{len(self.servers) + 1}",
            tenant_id=registration.tenant_id,
            name=registration.name,
            transport=registration.transport,
            status="registered",
            command=registration.command,
            url=registration.url,
            auth_type=registration.auth_type,
            timeout_ms=registration.timeout_ms,
            reconnect_policy=dict(registration.reconnect_policy),
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

    async def update_server(
        self,
        *,
        tenant_id: str,
        name: str,
        registration: McpServerRegistration,
    ) -> McpServerRecord | None:
        existing = await self.find_server_by_name(tenant_id=tenant_id, name=name)
        if existing is None:
            return None
        updated = McpServerRecord(
            id=existing.id,
            tenant_id=tenant_id,
            name=name,
            transport=registration.transport,
            status="registered",
            command=registration.command,
            url=registration.url,
            auth_type=registration.auth_type,
            timeout_ms=registration.timeout_ms,
            reconnect_policy=dict(registration.reconnect_policy),
        )
        self.servers[name] = updated
        return updated

    async def set_server_status(
        self,
        *,
        tenant_id: str,
        name: str,
        status: str,
    ) -> McpServerRecord | None:
        existing = await self.find_server_by_name(tenant_id=tenant_id, name=name)
        if existing is None:
            return None
        updated = replace(existing, status=status)
        self.servers[name] = updated
        return updated

    async def delete_server(self, *, tenant_id: str, name: str) -> bool:
        existing = await self.find_server_by_name(tenant_id=tenant_id, name=name)
        if existing is None:
            return False
        self.servers.pop(name, None)
        return True
