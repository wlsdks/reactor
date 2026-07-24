from __future__ import annotations

from datetime import UTC, datetime

from httpx import ASGITransport, AsyncClient

from reactor.api.app import create_app
from reactor.persistence.tool_store import ToolCatalogRecord

ADMIN_HEADERS = {
    "X-Reactor-User-Id": "admin_1",
    "X-Reactor-Tenant-Id": "tenant_1",
    "X-Reactor-Role": "ADMIN",
}


async def test_tool_catalog_api_requires_admin_and_persistence() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.get("/v1/admin/tools")
        unavailable = await client.get("/v1/admin/tools", headers=ADMIN_HEADERS)

    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == "admin access required"
    assert unavailable.status_code == 503
    assert unavailable.json()["detail"] == "tool catalog persistence is not configured"


async def test_tool_catalog_admin_crud_flow() -> None:
    store = FakeToolStore()
    app = create_app()
    app.state.reactor = FakeContainer(store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        created = await client.put(
            "/v1/admin/tools/builtin/search_docs",
            headers=ADMIN_HEADERS,
            json={
                "description": "Search approved docs.",
                "riskLevel": "read",
                "inputSchema": {"type": "object"},
                "outputSchema": {"type": "object"},
                "enabled": True,
                "timeoutMs": 15000,
            },
        )
        listed = await client.get("/v1/admin/tools", headers=ADMIN_HEADERS)
        fetched = await client.get("/api/admin/tools/builtin/search_docs", headers=ADMIN_HEADERS)
        disabled = await client.patch(
            "/v1/admin/tools/builtin/search_docs/enabled",
            headers=ADMIN_HEADERS,
            json={"enabled": False},
        )

    assert created.status_code == 200
    assert created.json()["qualifiedName"] == "builtin:search_docs"
    assert created.json()["requiresApproval"] is False
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert fetched.status_code == 200
    assert fetched.json()["timeoutMs"] == 15000
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False
    assert store.records[("tenant_1", "builtin", "search_docs")].enabled is False


async def test_tool_catalog_api_rejects_invalid_risk_level() -> None:
    app = create_app()
    app.state.reactor = FakeContainer(FakeToolStore())
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.put(
            "/v1/admin/tools/builtin/search_docs",
            headers=ADMIN_HEADERS,
            json={
                "description": "Search approved docs.",
                "riskLevel": "unknown",
                "inputSchema": {"type": "object"},
                "outputSchema": {"type": "object"},
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "invalid tool risk_level: unknown"


class FakeContainer:
    def __init__(self, store: FakeToolStore | None) -> None:
        self._store = store

    def tool_store(self) -> FakeToolStore | None:
        return self._store


class FakeToolStore:
    def __init__(self) -> None:
        self.records: dict[tuple[str, str, str], ToolCatalogRecord] = {}

    async def save(self, record: ToolCatalogRecord) -> ToolCatalogRecord:
        record.validate()
        self.records[(record.tenant_id, record.namespace, record.name)] = record
        return record

    async def list_catalog(self, *, tenant_id: str) -> list[ToolCatalogRecord]:
        return [record for key, record in self.records.items() if key[0] == tenant_id]

    async def find_catalog(
        self,
        *,
        tenant_id: str,
        namespace: str,
        name: str,
    ) -> ToolCatalogRecord | None:
        return self.records.get((tenant_id, namespace, name))


FIXED_TIME = datetime(2026, 6, 27, 12, 0, tzinfo=UTC)
