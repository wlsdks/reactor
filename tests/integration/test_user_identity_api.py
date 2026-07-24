from __future__ import annotations

from datetime import UTC, datetime

from httpx import ASGITransport, AsyncClient

from reactor.api.app import create_app
from reactor.auth.models import UserIdentityRecord
from reactor.core.settings import Settings

ADMIN_HEADERS = {
    "X-Reactor-Role": "ADMIN",
    "X-Reactor-User-Id": "admin_1",
    "X-Reactor-Tenant-Id": "tenant_1",
}

USER_HEADERS = {
    "X-Reactor-Role": "USER",
    "X-Reactor-User-Id": "user_1",
    "X-Reactor-Tenant-Id": "tenant_1",
}


async def test_user_identity_admin_api_upserts_looks_up_and_lists_mappings() -> None:
    identity_store = FakeUserIdentityStore()
    app = create_app()
    app.state.reactor = FakeContainer(identity_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.put(
            "/api/admin/user-identities",
            headers=USER_HEADERS,
            json={
                "userId": "user_1",
                "provider": "jira",
                "externalSubject": "acct-123",
                "metadata": {"workspace": "ENG"},
            },
        )
        upserted = await client.put(
            "/api/admin/user-identities",
            headers=ADMIN_HEADERS,
            json={
                "userId": "user_1",
                "provider": "jira",
                "externalSubject": "acct-123",
                "metadata": {"workspace": "ENG"},
            },
        )
        found = await client.get(
            "/v1/admin/user-identities/by-external-subject",
            headers=ADMIN_HEADERS,
            params={"provider": "jira", "externalSubject": "acct-123"},
        )
        list_forbidden = await client.get(
            "/api/admin/user-identities",
            headers=USER_HEADERS,
        )
        list_all = await client.get(
            "/v1/admin/user-identities",
            headers=ADMIN_HEADERS,
        )
        listed = await client.get(
            "/api/admin/users/user_1/identities",
            headers=ADMIN_HEADERS,
        )
        missing = await client.get(
            "/api/admin/user-identities/by-external-subject",
            headers=ADMIN_HEADERS,
            params={"provider": "jira", "externalSubject": "missing"},
        )
        forbidden_delete = await client.delete(
            "/api/admin/user-identities/by-external-subject",
            headers=USER_HEADERS,
            params={"provider": "jira", "externalSubject": "acct-123"},
        )
        deleted = await client.delete(
            "/v1/admin/user-identities/by-external-subject",
            headers=ADMIN_HEADERS,
            params={"provider": "jira", "externalSubject": "acct-123"},
        )
        delete_missing = await client.delete(
            "/api/admin/user-identities/by-external-subject",
            headers=ADMIN_HEADERS,
            params={"provider": "jira", "externalSubject": "missing"},
        )
        listed_after_delete = await client.get(
            "/api/admin/users/user_1/identities",
            headers=ADMIN_HEADERS,
        )

    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "forbidden"
    assert upserted.status_code == 200
    assert upserted.json() == {
        "id": "identity_1",
        "tenantId": "tenant_1",
        "userId": "user_1",
        "provider": "jira",
        "externalSubject": "acct-123",
        "metadata": {"workspace": "ENG"},
        "createdAt": "2026-06-01T00:00:00Z",
        "updatedAt": "2026-06-02T00:00:00Z",
    }
    assert found.status_code == 200
    assert found.json()["externalSubject"] == "acct-123"
    assert list_forbidden.status_code == 403
    assert list_forbidden.json()["code"] == "forbidden"
    assert list_all.status_code == 200
    assert list_all.json()["items"] == [upserted.json()]
    assert listed.status_code == 200
    assert listed.json()["items"] == [upserted.json()]
    assert missing.status_code == 404
    assert missing.json()["detail"] == "user identity mapping not found"
    assert forbidden_delete.status_code == 403
    assert forbidden_delete.json()["code"] == "forbidden"
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert delete_missing.status_code == 404
    assert delete_missing.json()["detail"] == "user identity mapping not found"
    assert listed_after_delete.status_code == 200
    assert listed_after_delete.json()["items"] == []
    assert identity_store.upsert_calls == [
        {
            "tenant_id": "tenant_1",
            "user_id": "user_1",
            "provider": "jira",
            "external_subject": "acct-123",
            "metadata": {"workspace": "ENG"},
        }
    ]


async def test_user_identity_admin_api_requires_persistence() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/api/admin/users/user_1/identities",
            headers=ADMIN_HEADERS,
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "user identity persistence is not configured"


class FakeContainer:
    def __init__(self, identity_store: FakeUserIdentityStore | None = None) -> None:
        self.settings = Settings()
        self._identity_store = identity_store

    def user_identity_store(self) -> FakeUserIdentityStore | None:
        return self._identity_store


class FakeUserIdentityStore:
    def __init__(self) -> None:
        self.records: dict[tuple[str, str, str], UserIdentityRecord] = {}
        self.upsert_calls: list[dict[str, object]] = []

    async def upsert(
        self,
        *,
        tenant_id: str,
        provider: str,
        external_subject: str,
        user_id: str,
        metadata: dict[str, object] | None = None,
    ) -> UserIdentityRecord:
        self.upsert_calls.append(
            {
                "tenant_id": tenant_id,
                "user_id": user_id,
                "provider": provider,
                "external_subject": external_subject,
                "metadata": dict(metadata or {}),
            }
        )
        record = UserIdentityRecord(
            id="identity_1",
            tenant_id=tenant_id,
            user_id=user_id,
            provider=provider,
            external_subject=external_subject,
            metadata=dict(metadata or {}),
            created_at=datetime(2026, 6, 1, tzinfo=UTC),
            updated_at=datetime(2026, 6, 2, tzinfo=UTC),
        )
        self.records[(tenant_id, provider, external_subject)] = record
        return record

    async def find_by_external_subject(
        self,
        *,
        tenant_id: str,
        provider: str,
        external_subject: str,
    ) -> UserIdentityRecord | None:
        return self.records.get((tenant_id, provider, external_subject))

    async def list_for_user(self, *, tenant_id: str, user_id: str) -> list[UserIdentityRecord]:
        return [
            record
            for record in self.records.values()
            if record.tenant_id == tenant_id and record.user_id == user_id
        ]

    async def list_all(self, *, tenant_id: str) -> list[UserIdentityRecord]:
        return [record for record in self.records.values() if record.tenant_id == tenant_id]

    async def delete_by_external_subject(
        self,
        *,
        tenant_id: str,
        provider: str,
        external_subject: str,
    ) -> bool:
        return self.records.pop((tenant_id, provider, external_subject), None) is not None
