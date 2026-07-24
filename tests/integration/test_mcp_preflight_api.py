from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import httpx
import respx
from httpx import ASGITransport, AsyncClient

from reactor.admin.audit import AdminAuditAction, AdminAuditLog
from reactor.api.app import create_app
from reactor.core.settings import Settings
from reactor.mcp.admin_preflight import preflight_hmac_signature
from reactor.mcp.registry import McpServerRegistration

ADMIN_HEADERS = {
    "X-Reactor-User-Id": "admin_1",
    "X-Reactor-Tenant-Id": "tenant_1",
    "X-Reactor-Role": "ADMIN",
    "X-Request-Id": "req_1",
}
USER_HEADERS = {
    "X-Reactor-User-Id": "user_1",
    "X-Reactor-Tenant-Id": "tenant_1",
    "X-Reactor-Role": "USER",
}
TEST_HMAC_SECRET = "hmac" + "-secret"


async def test_mcp_preflight_rejects_non_admin_and_missing_server() -> None:
    app = create_app()
    app.state.reactor = FakeContainer(FakeMcpRegistryStore({}), FakeAdminAuditStore())
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.get("/api/mcp/servers/docs/preflight", headers=USER_HEADERS)
        missing = await client.get("/v1/mcp/servers/docs/preflight", headers=ADMIN_HEADERS)

    assert forbidden.status_code == 403
    assert missing.status_code == 404
    assert missing.json() == {"error": "MCP server 'docs' not found"}


async def test_mcp_preflight_skips_when_no_scoped_admin_token() -> None:
    audits = FakeAdminAuditStore()
    app = create_app()
    app.state.reactor = FakeContainer(
        FakeMcpRegistryStore(
            {
                "docs": McpServerRecord(
                    name="docs",
                    url="https://mcp.example.com/mcp",
                    timeout_ms=15_000,
                    reconnect_policy={},
                )
            }
        ),
        audits,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/mcp/servers/docs/preflight", headers=ADMIN_HEADERS)

    assert response.status_code == 204
    assert response.headers["X-Preflight-Skipped"] == "no-admin-token"
    assert audits.saved[0].category == "mcp_preflight"
    assert audits.saved[0].action == AdminAuditAction.READ
    assert audits.saved[0].detail == "status=204"


@respx.mock
async def test_mcp_preflight_proxies_upstream_json_and_records_audit() -> None:
    route = respx.get("https://mcp.example.com/admin/preflight").mock(
        return_value=httpx.Response(
            200,
            json={
                "ok": True,
                "readyForProduction": False,
                "policySource": "dynamic",
                "summary": {"passCount": 7, "warnCount": 1, "failCount": 0},
            },
        )
    )
    audits = FakeAdminAuditStore()
    app = create_app()
    app.state.reactor = FakeContainer(
        FakeMcpRegistryStore(
            {
                "docs": McpServerRecord(
                    name="docs",
                    url="https://mcp.example.com/mcp",
                    timeout_ms=15_000,
                    reconnect_policy={"adminToken": "admin-secret"},
                )
            }
        ),
        audits,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/v1/mcp/servers/docs/preflight", headers=ADMIN_HEADERS)

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert route.called
    upstream_request = cast(httpx.Request, route.calls[0].request)
    assert upstream_request.headers["X-Admin-Token"] == "admin-secret"
    assert upstream_request.headers["X-Admin-Actor"] == "admin_1"
    assert upstream_request.headers["X-Request-Id"] == "req_1"
    assert audits.saved[0].detail == (
        "status=200, policySource=dynamic, ok=true, readyForProduction=false, "
        "passCount=7, warnCount=1, failCount=0"
    )


@respx.mock
async def test_mcp_preflight_adds_hmac_headers_when_configured() -> None:
    route = respx.get("https://mcp.example.com/admin/preflight").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    app = create_app()
    app.state.reactor = FakeContainer(
        FakeMcpRegistryStore(
            {
                "docs": McpServerRecord(
                    name="docs",
                    url="https://mcp.example.com/sse",
                    timeout_ms=15_000,
                    reconnect_policy={
                        "adminToken": "admin-secret",
                        "adminHmacSecret": TEST_HMAC_SECRET,
                        "adminHmacRequired": True,
                    },
                )
            }
        ),
        FakeAdminAuditStore(),
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/api/mcp/servers/docs/preflight",
            headers={**ADMIN_HEADERS, "X-Admin-Timestamp": "1782547200"},
        )

    assert response.status_code == 200
    upstream_request = cast(httpx.Request, route.calls[0].request)
    assert upstream_request.headers["X-Admin-Timestamp"] == "1782547200"
    assert upstream_request.headers["X-Admin-Signature"] == preflight_hmac_signature(
        secret=TEST_HMAC_SECRET,
        method="GET",
        path="/admin/preflight",
        query="",
        body="",
        timestamp="1782547200",
    )


class FakeContainer:
    def __init__(
        self,
        mcp_store: FakeMcpRegistryStore,
        audit_store: FakeAdminAuditStore,
    ) -> None:
        self.settings = Settings()
        self._mcp_store = mcp_store
        self._audit_store = audit_store

    def mcp_registry_store(self) -> FakeMcpRegistryStore:
        return self._mcp_store

    def admin_audit_store(self) -> FakeAdminAuditStore:
        return self._audit_store


@dataclass(frozen=True)
class McpServerRecord:
    name: str
    url: str
    timeout_ms: int
    reconnect_policy: dict[str, Any]


class FakeMcpRegistryStore:
    def __init__(self, servers: dict[str, McpServerRecord]) -> None:
        self.servers = servers

    async def register_server(self, registration: McpServerRegistration) -> str:
        del registration
        raise NotImplementedError

    async def list_servers(self, tenant_id: str) -> list[McpServerRecord]:
        del tenant_id
        return list(self.servers.values())

    async def find_server_by_name(self, *, tenant_id: str, name: str) -> McpServerRecord | None:
        del tenant_id
        return self.servers.get(name)


class FakeAdminAuditStore:
    def __init__(self) -> None:
        self.saved: list[AdminAuditLog] = []

    async def save(self, record: AdminAuditLog, *, tenant_id: str) -> AdminAuditLog:
        del tenant_id
        self.saved.append(record)
        return record
