from __future__ import annotations

from datetime import UTC, datetime

from httpx import ASGITransport, AsyncClient

from reactor.api.app import create_app
from reactor.core.settings import Settings
from reactor.memory.service import UserMemoryRecord


async def test_user_memory_requires_configured_persistence_after_auth() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/api/user-memory/user_1",
            headers={"X-Reactor-User-Id": "user_1", "X-Reactor-Tenant-Id": "tenant_1"},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "user memory persistence is not configured"


async def test_user_memory_get_update_and_delete_flow() -> None:
    store = FakeUserMemoryStore()
    app = create_app()
    app.state.reactor = FakeContainer(store)
    transport = ASGITransport(app=app)
    headers = {"X-Reactor-User-Id": "user_1", "X-Reactor-Tenant-Id": "tenant_1"}

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        missing = await client.get("/api/user-memory/user_1", headers=headers)
        fact = await client.put(
            "/api/user-memory/user_1/facts",
            headers=headers,
            json={"key": "team", "value": "platform"},
        )
        preference = await client.put(
            "/v1/user-memory/user_1/preferences",
            headers=headers,
            json={"key": "language", "value": "Korean"},
        )
        memory = await client.get("/api/user-memory/user_1", headers=headers)
        deleted = await client.delete("/v1/user-memory/user_1", headers=headers)
        after_delete = await client.get("/api/user-memory/user_1", headers=headers)

    assert missing.status_code == 404
    assert fact.status_code == 200
    assert fact.json() == {"updated": True}
    assert preference.status_code == 200
    assert memory.status_code == 200
    assert memory.json()["facts"] == {"team": "platform"}
    assert memory.json()["preferences"] == {"language": "Korean"}
    assert deleted.status_code == 204
    assert after_delete.status_code == 404


async def test_user_memory_denies_cross_user_and_anonymous_access() -> None:
    store = FakeUserMemoryStore()
    app = create_app()
    app.state.reactor = FakeContainer(store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        cross_user = await client.get(
            "/api/user-memory/user_1",
            headers={"X-Reactor-User-Id": "user_2", "X-Reactor-Tenant-Id": "tenant_1"},
        )
        anonymous_path = await client.get(
            "/api/user-memory/anonymous",
            headers={"X-Reactor-User-Id": "anonymous", "X-Reactor-Tenant-Id": "tenant_1"},
        )
        missing_auth = await client.get("/api/user-memory/anonymous")

    assert cross_user.status_code == 403
    assert anonymous_path.status_code == 403
    assert missing_auth.status_code == 403


class FakeContainer:
    def __init__(self, store: FakeUserMemoryStore | None) -> None:
        self.settings = Settings()
        self._store = store

    def memory_store(self) -> FakeUserMemoryStore | None:
        return self._store


class FakeUserMemoryStore:
    def __init__(self) -> None:
        self.records: dict[tuple[str, str], UserMemoryRecord] = {}

    async def get_user_memory(self, *, tenant_id: str, user_id: str) -> UserMemoryRecord | None:
        return self.records.get((tenant_id, user_id))

    async def upsert_user_memory_value(
        self,
        *,
        tenant_id: str,
        user_id: str,
        category: str,
        key: str,
        value: str,
    ) -> None:
        existing = self.records.get((tenant_id, user_id))
        facts = dict(existing.facts if existing else {})
        preferences = dict(existing.preferences if existing else {})
        if category == "fact":
            facts[key] = value
        elif category == "preference":
            preferences[key] = value
        self.records[(tenant_id, user_id)] = UserMemoryRecord(
            user_id=user_id,
            facts=facts,
            preferences=preferences,
            recent_topics=list(existing.recent_topics if existing else []),
            updated_at=datetime.now(UTC),
        )

    async def delete_user_memory(self, *, tenant_id: str, user_id: str) -> None:
        self.records.pop((tenant_id, user_id), None)
