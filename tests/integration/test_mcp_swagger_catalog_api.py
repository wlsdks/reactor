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
    "X-Request-Id": "req_swagger_1",
}
USER_HEADERS = {
    "X-Reactor-User-Id": "user_1",
    "X-Reactor-Tenant-Id": "tenant_1",
    "X-Reactor-Role": "USER",
}
TEST_HMAC_SECRET = "swagger" + "-hmac"


async def test_swagger_sources_reject_non_admin_and_downgrade_no_admin_token() -> None:
    audits = FakeAdminAuditStore()
    app = create_app()
    app.state.reactor = FakeContainer(
        FakeMcpRegistryStore(
            {
                "swagger": McpServerRecord(
                    name="swagger",
                    url="https://mcp.example.com/sse",
                    timeout_ms=15_000,
                    reconnect_policy={},
                )
            }
        ),
        audits,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.get(
            "/api/mcp/servers/swagger/swagger/sources",
            headers=USER_HEADERS,
        )
        response = await client.get(
            "/api/mcp/servers/swagger/swagger/sources",
            headers=ADMIN_HEADERS,
        )

    assert forbidden.status_code == 403
    assert response.status_code == 200
    assert response.json() == []
    assert response.headers["X-Mcp-Admin-Available"] == "false"
    assert response.headers["X-Mcp-Admin-Reason"] == "no-admin-token"
    assert audits.saved == []


@respx.mock
async def test_swagger_sources_proxy_list_and_create_with_metadata_and_audit() -> None:
    list_route = respx.get("https://mcp.example.com/admin/spec-sources").mock(
        return_value=httpx.Response(200, json=[{"name": "payments", "enabled": True}])
    )
    create_route = respx.post("https://mcp.example.com/admin/spec-sources").mock(
        return_value=httpx.Response(201, json={"name": "payments", "ownerTeam": "platform"})
    )
    audits = FakeAdminAuditStore()
    app = create_app()
    app.state.reactor = FakeContainer(
        FakeMcpRegistryStore({"swagger": server_record()}),
        audits,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        listed = await client.get(
            "/v1/mcp/servers/swagger/swagger/sources",
            headers=ADMIN_HEADERS,
        )
        created = await client.post(
            "/api/mcp/servers/swagger/swagger/sources",
            headers=ADMIN_HEADERS,
            json={
                "name": "payments",
                "url": "https://example.com/openapi.json",
                "enabled": True,
                "jiraProjectKey": "PAY",
                "confluenceSpaceKey": "PAYMENTS",
                "bitbucketRepository": "team/payments",
                "serviceSlug": "payments-api",
                "ownerTeam": "platform",
            },
        )

    assert listed.status_code == 200
    assert listed.json() == [{"name": "payments", "enabled": True}]
    assert created.status_code == 201
    create_request = cast(httpx.Request, create_route.calls[0].request)
    assert create_request.headers["X-Admin-Token"] == "admin-secret"
    assert create_request.headers["X-Admin-Actor"] == "admin_1"
    assert create_request.headers["X-Request-Id"] == "req_swagger_1"
    assert '"jiraProjectKey":"PAY"' in create_request.content.decode()
    assert '"ownerTeam":"platform"' in create_request.content.decode()
    assert list_route.called
    assert [audit.action for audit in audits.saved] == [
        AdminAuditAction.LIST_SOURCES,
        AdminAuditAction.CREATE_SOURCE,
    ]
    assert audits.saved[-1].detail == "status=201, detail=payments"


@respx.mock
async def test_swagger_revisions_diff_and_publish_forward_query_body_and_hmac() -> None:
    revisions_route = respx.get(
        "https://mcp.example.com/admin/spec-sources/payments/revisions?limit=5"
    ).mock(return_value=httpx.Response(200, json=[{"id": "rev-2"}]))
    diff_route = respx.get(
        "https://mcp.example.com/admin/spec-sources/payments/diff?from=rev+1&to=rev/2"
    ).mock(return_value=httpx.Response(200, json={"endpointsAdded": ["POST /v2/payments"]}))
    publish_route = respx.post("https://mcp.example.com/admin/spec-sources/payments/publish").mock(
        return_value=httpx.Response(200, json={"revisionId": "rev-2"})
    )
    app = create_app()
    app.state.reactor = FakeContainer(
        FakeMcpRegistryStore(
            {
                "swagger": McpServerRecord(
                    name="swagger",
                    url="https://mcp.example.com/mcp",
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
        revisions = await client.get(
            "/api/mcp/servers/swagger/swagger/sources/payments/revisions",
            params={"limit": 5},
            headers=ADMIN_HEADERS,
        )
        diff = await client.get(
            "/api/mcp/servers/swagger/swagger/sources/payments/diff",
            params={"from": "rev 1", "to": "rev/2"},
            headers=ADMIN_HEADERS,
        )
        published = await client.post(
            "/api/mcp/servers/swagger/swagger/sources/payments/publish",
            headers={**ADMIN_HEADERS, "X-Admin-Timestamp": "1782547200"},
            json={"revisionId": "rev-2"},
        )

    assert revisions.status_code == 200
    assert diff.status_code == 200
    assert published.status_code == 200
    assert revisions_route.called
    assert diff_route.called
    publish_request = cast(httpx.Request, publish_route.calls[0].request)
    assert publish_request.content.decode() == '{"revisionId":"rev-2"}'
    assert publish_request.headers["X-Admin-Signature"] == preflight_hmac_signature(
        secret=TEST_HMAC_SECRET,
        method="POST",
        path="/admin/spec-sources/payments/publish",
        query="",
        body='{"revisionId":"rev-2"}',
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

    def runtime_settings_store(self) -> None:
        return None


@dataclass(frozen=True)
class McpServerRecord:
    name: str
    url: str
    timeout_ms: int
    reconnect_policy: dict[str, Any]


def server_record() -> McpServerRecord:
    return McpServerRecord(
        name="swagger",
        url="https://mcp.example.com/sse",
        timeout_ms=15_000,
        reconnect_policy={"adminToken": "admin-secret"},
    )


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
