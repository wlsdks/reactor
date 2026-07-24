from __future__ import annotations

from httpx import ASGITransport, AsyncClient

from reactor.api.app import create_app
from reactor.core.settings import Settings
from reactor.guards.intents import InMemoryIntentRegistry

ADMIN_HEADERS = {
    "X-Reactor-User-Id": "admin_1",
    "X-Reactor-Tenant-Id": "tenant_1",
    "X-Reactor-Role": "ADMIN",
}


async def test_intents_require_admin_and_configured_registry() -> None:
    app = create_app()
    app.state.reactor = MissingRegistryContainer()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.get("/api/intents")
        unavailable = await client.get("/api/intents", headers=ADMIN_HEADERS)

    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == "permission required: guard:read"
    assert unavailable.status_code == 503
    assert unavailable.json()["detail"] == "intent registry persistence is not configured"


async def test_intent_crud_ports_legacy_contract() -> None:
    registry = InMemoryIntentRegistry()
    app = create_app()
    app.state.reactor = FakeContainer(registry)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        created = await client.post(
            "/api/intents",
            headers=ADMIN_HEADERS,
            json={
                "name": "support_ticket",
                "description": "Classifies support ticket creation requests",
                "examples": ["create a ticket"],
                "keywords": ["ticket", "support"],
                "profile": "support",
                "enabled": True,
            },
        )
        duplicate = await client.post(
            "/v1/intents",
            headers=ADMIN_HEADERS,
            json={
                "name": "support_ticket",
                "description": "Duplicate",
            },
        )
        listed = await client.get("/v1/intents", headers=ADMIN_HEADERS)
        fetched = await client.get("/api/intents/support_ticket", headers=ADMIN_HEADERS)
        updated = await client.put(
            "/v1/intents/support_ticket",
            headers=ADMIN_HEADERS,
            json={
                "description": "Updated support classifier",
                "keywords": ["helpdesk"],
                "enabled": False,
            },
        )
        missing = await client.get("/api/intents/missing", headers=ADMIN_HEADERS)
        deleted = await client.delete("/api/intents/support_ticket", headers=ADMIN_HEADERS)

    assert created.status_code == 201
    assert created.json() == {
        "name": "support_ticket",
        "description": "Classifies support ticket creation requests",
        "examples": ["create a ticket"],
        "keywords": ["ticket", "support"],
        "profile": "support",
        "enabled": True,
    }
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "Intent 'support_ticket' already exists"
    assert listed.status_code == 200
    assert [intent["name"] for intent in listed.json()] == ["support_ticket"]
    assert fetched.status_code == 200
    assert fetched.json()["profile"] == "support"
    assert updated.status_code == 200
    assert updated.json()["description"] == "Updated support classifier"
    assert updated.json()["examples"] == ["create a ticket"]
    assert updated.json()["keywords"] == ["helpdesk"]
    assert updated.json()["enabled"] is False
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Intent not found: missing"
    assert deleted.status_code == 204
    assert await registry.get("support_ticket") is None


class FakeContainer:
    def __init__(self, registry: InMemoryIntentRegistry) -> None:
        self.settings = Settings()
        self._registry = registry

    def intent_registry(self) -> InMemoryIntentRegistry:
        return self._registry


class MissingRegistryContainer:
    settings = Settings()
