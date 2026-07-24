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


async def test_rag_ingestion_policy_requires_admin_and_configured_store() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.get("/api/rag-ingestion/policy", headers=USER_HEADERS)
        unavailable = await client.get("/api/rag-ingestion/policy", headers=ADMIN_HEADERS)

    assert forbidden.status_code == 403
    assert forbidden.json()["error"] == "관리자 권한이 필요합니다"
    assert unavailable.status_code == 503
    assert unavailable.json()["error"] == "RagIngestionPolicyStore 미등록 — DB 미구성"


async def test_rag_ingestion_policy_get_update_delete_and_audit() -> None:
    settings = Settings(
        rag_ingestion_enabled=True,
        rag_ingestion_dynamic_enabled=True,
        rag_ingestion_require_review=False,
        rag_ingestion_allowed_channels=["slack", "email"],
        rag_ingestion_min_query_chars=5,
        rag_ingestion_min_response_chars=15,
        rag_ingestion_blocked_patterns=["password"],
    )
    runtime_store = FakeRuntimeSettingsStore()
    audits = FakeAdminAuditStore()
    app = create_app()
    app.state.reactor = FakeContainer(
        settings=settings,
        runtime_settings_store=runtime_store,
        admin_audit_store=audits,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        initial = await client.get("/api/rag-ingestion/policy", headers=ADMIN_HEADERS)
        updated = await client.put(
            "/v1/rag-ingestion/policy",
            headers=ADMIN_HEADERS,
            json={
                "enabled": True,
                "requireReview": True,
                "allowedChannels": ["Slack", "  confluence  ", ""],
                "minQueryChars": 0,
                "minResponseChars": -2,
                "blockedPatterns": [" secret ", ""],
            },
        )
        after_update = await client.get("/v1/rag-ingestion/policy", headers=ADMIN_HEADERS)
        deleted = await client.delete("/api/rag-ingestion/policy", headers=ADMIN_HEADERS)
        after_delete = await client.get("/api/rag-ingestion/policy", headers=ADMIN_HEADERS)

    assert initial.status_code == 200
    assert initial.json()["configEnabled"] is True
    assert initial.json()["dynamicEnabled"] is True
    assert initial.json()["stored"] is None
    assert initial.json()["effective"]["allowedChannels"] == ["email", "slack"]
    assert initial.json()["effective"]["requireReview"] is False

    assert updated.status_code == 200
    assert updated.json()["allowedChannels"] == ["confluence", "slack"]
    assert updated.json()["minQueryChars"] == 1
    assert updated.json()["minResponseChars"] == 1
    assert updated.json()["blockedPatterns"] == ["secret"]
    assert isinstance(updated.json()["createdAt"], int)

    assert after_update.status_code == 200
    assert after_update.json()["stored"]["allowedChannels"] == ["confluence", "slack"]
    assert after_update.json()["effective"]["allowedChannels"] == ["confluence", "slack"]

    assert deleted.status_code == 204
    assert after_delete.status_code == 200
    assert after_delete.json()["stored"] is None
    assert after_delete.json()["effective"]["allowedChannels"] == ["email", "slack"]
    assert [audit.action for audit in audits.saved] == [
        AdminAuditAction.UPDATE,
        AdminAuditAction.DELETE,
    ]
    assert audits.saved[0].category == "rag_ingestion_policy"
    assert audits.saved[0].resource_id == "singleton"


async def test_rag_ingestion_policy_rejects_invalid_blocked_pattern() -> None:
    app = create_app()
    app.state.reactor = FakeContainer(
        runtime_settings_store=FakeRuntimeSettingsStore(),
        admin_audit_store=FakeAdminAuditStore(),
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.put(
            "/api/rag-ingestion/policy",
            headers=ADMIN_HEADERS,
            json={"blockedPatterns": ["["]},
        )

    assert response.status_code == 400
    assert response.json()["error"] == "유효하지 않은 정규식 패턴: [..."


async def test_rag_ingestion_policy_accepts_legacy_blocked_pattern_count_limit() -> None:
    app = create_app()
    app.state.reactor = FakeContainer(
        runtime_settings_store=FakeRuntimeSettingsStore(),
        admin_audit_store=FakeAdminAuditStore(),
    )
    transport = ASGITransport(app=app)
    patterns = [f"pattern_{index}" for index in range(250)]

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.put(
            "/api/rag-ingestion/policy",
            headers=ADMIN_HEADERS,
            json={"blockedPatterns": patterns},
        )

    assert response.status_code == 200
    assert len(response.json()["blockedPatterns"]) == 250


class FakeContainer:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        runtime_settings_store: FakeRuntimeSettingsStore | None = None,
        admin_audit_store: FakeAdminAuditStore | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self._runtime_settings_store = runtime_settings_store
        self._admin_audit_store = admin_audit_store

    def runtime_settings_store(self) -> FakeRuntimeSettingsStore | None:
        return self._runtime_settings_store

    def admin_audit_store(self) -> FakeAdminAuditStore | None:
        return self._admin_audit_store


class FakeRuntimeSettingsStore:
    def __init__(self) -> None:
        self.records: dict[tuple[str, str], RuntimeSettingRecord] = {}

    async def set(self, update: RuntimeSettingUpdate) -> RuntimeSettingRecord:
        record = RuntimeSettingRecord(
            tenant_id=update.tenant_id,
            key=update.key,
            value=update.value,
            value_type=update.value_type,
            category=update.category,
            description=update.description,
            updated_by=update.updated_by,
            updated_at=datetime.now(UTC),
            metadata=update.metadata,
        )
        self.records[(record.tenant_id, record.key)] = record
        return record

    async def find(
        self,
        key: str,
        *,
        tenant_id: str = "global",
    ) -> RuntimeSettingRecord | None:
        return self.records.get((tenant_id, key))

    async def delete(self, key: str, *, tenant_id: str = "global") -> None:
        self.records.pop((tenant_id, key), None)


class FakeAdminAuditStore:
    def __init__(self) -> None:
        self.saved: list[AdminAuditLog] = []

    async def save(self, log: AdminAuditLog, *, tenant_id: str = "tenant_1") -> AdminAuditLog:
        del tenant_id
        self.saved.append(log)
        return log
