from __future__ import annotations

from datetime import UTC, datetime

from httpx import ASGITransport, AsyncClient

from reactor.admin.audit import AdminAuditAction, AdminAuditLog
from reactor.agents.specs import AgentSpecRecord
from reactor.api.app import create_app
from reactor.core.settings import Settings

ADMIN_HEADERS = {"X-Reactor-Role": "ADMIN", "X-Reactor-User-Id": "admin_1"}
USER_HEADERS = {"X-Reactor-Role": "USER", "X-Reactor-User-Id": "user_1"}


async def test_agent_specs_require_admin_and_configured_store() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.get("/api/admin/agent-specs", headers=USER_HEADERS)
        unavailable = await client.get("/api/admin/agent-specs", headers=ADMIN_HEADERS)

    assert forbidden.status_code == 403
    assert forbidden.json()["error"] == "관리자 권한이 필요합니다"
    assert unavailable.status_code == 503
    assert unavailable.json()["error"] == "AgentSpecStore 미등록 — DB 미구성"


async def test_agent_specs_crud_ports_legacy_contract_and_audits_prompt_reads() -> None:
    store = FakeAgentSpecStore()
    audits = FakeAdminAuditStore()
    app = create_app()
    app.state.reactor = FakeContainer(agent_spec_store=store, admin_audit_store=audits)
    transport = ASGITransport(app=app)
    long_prompt = "p" * 130

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        created = await client.post(
            "/api/admin/agent-specs",
            headers=ADMIN_HEADERS,
            json={
                "name": "translator",
                "description": "Translation agent",
                "toolNames": ["translate"],
                "keywords": ["translation"],
                "systemPrompt": long_prompt,
                "independentExecution": False,
            },
        )
        spec_id = created.json()["id"]
        duplicate = await client.post(
            "/v1/admin/agent-specs",
            headers=ADMIN_HEADERS,
            json={"name": "translator"},
        )
        blank_name = await client.post(
            "/v1/admin/agent-specs",
            headers=ADMIN_HEADERS,
            json={"name": "   "},
        )
        listed = await client.get("/v1/admin/agent-specs", headers=ADMIN_HEADERS)
        enabled = await client.get("/api/admin/agent-specs?enabled=true", headers=ADMIN_HEADERS)
        fetched = await client.get(f"/api/admin/agent-specs/{spec_id}", headers=ADMIN_HEADERS)
        prompt = await client.get(
            f"/v1/admin/agent-specs/{spec_id}/system-prompt",
            headers=ADMIN_HEADERS,
        )
        invalid_update = await client.put(
            f"/api/admin/agent-specs/{spec_id}",
            headers=ADMIN_HEADERS,
            json={"mode": "INVALID"},
        )
        updated = await client.put(
            f"/v1/admin/agent-specs/{spec_id}",
            headers=ADMIN_HEADERS,
            json={"mode": "PLAN_EXECUTE", "enabled": False},
        )
        missing = await client.get("/api/admin/agent-specs/missing", headers=ADMIN_HEADERS)
        deleted = await client.delete(f"/api/admin/agent-specs/{spec_id}", headers=ADMIN_HEADERS)

    assert created.status_code == 201
    assert created.json()["name"] == "translator"
    assert created.json()["mode"] == "REACT"
    assert created.json()["independentExecution"] is False
    assert created.json()["hasSystemPrompt"] is True
    assert created.json()["systemPromptPreview"] == ("p" * 120) + "\u2026"
    assert duplicate.status_code == 409
    assert duplicate.json()["error"] == "이름 'translator'은 이미 사용 중입니다"
    assert blank_name.status_code == 422
    assert listed.status_code == 200
    assert [record["name"] for record in listed.json()] == ["translator"]
    assert enabled.status_code == 200
    assert [record["name"] for record in enabled.json()] == ["translator"]
    assert fetched.status_code == 200
    assert fetched.json()["systemPromptPreview"] == ("p" * 120) + "\u2026"
    assert prompt.status_code == 200
    assert prompt.json() == {"systemPrompt": long_prompt}
    assert invalid_update.status_code == 400
    assert invalid_update.json()["error"] == "유효하지 않은 모드: INVALID"
    assert updated.status_code == 200
    assert updated.json()["mode"] == "PLAN_EXECUTE"
    assert updated.json()["enabled"] is False
    assert missing.status_code == 404
    assert missing.json()["error"] == "에이전트 스펙을 찾을 수 없습니다: missing"
    assert deleted.status_code == 204
    assert await store.get(spec_id) is None
    assert [audit.action for audit in audits.saved] == [
        AdminAuditAction.CREATE,
        AdminAuditAction.READ,
        AdminAuditAction.UPDATE,
        AdminAuditAction.DELETE,
    ]
    assert audits.saved[1].resource_type == "agent_spec_system_prompt"


async def test_agent_specs_create_rejects_invalid_mode_before_store_write() -> None:
    store = FakeAgentSpecStore()
    app = create_app()
    app.state.reactor = FakeContainer(agent_spec_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/admin/agent-specs",
            headers=ADMIN_HEADERS,
            json={"name": "bad", "mode": "INVALID"},
        )

    assert response.status_code == 400
    assert response.json()["error"] == "유효하지 않은 모드: INVALID"
    assert store.records == {}


async def test_agent_specs_update_rejects_duplicate_name_before_store_write() -> None:
    store = FakeAgentSpecStore()
    first = await store.save(AgentSpecRecord(id="spec_1", name="translator"))
    second = await store.save(AgentSpecRecord(id="spec_2", name="coder"))
    app = create_app()
    app.state.reactor = FakeContainer(agent_spec_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        duplicate = await client.put(
            f"/api/admin/agent-specs/{second.id}",
            headers=ADMIN_HEADERS,
            json={"name": first.name},
        )

    assert duplicate.status_code == 409
    assert duplicate.json()["error"] == "이름 'translator'은 이미 사용 중입니다"
    unchanged = await store.get(second.id)
    assert unchanged is not None
    assert unchanged.name == "coder"


class FakeContainer:
    def __init__(
        self,
        *,
        agent_spec_store: FakeAgentSpecStore | None = None,
        admin_audit_store: FakeAdminAuditStore | None = None,
    ) -> None:
        self.settings = Settings()
        self._agent_spec_store = agent_spec_store
        self._admin_audit_store = admin_audit_store

    def agent_spec_store(self) -> FakeAgentSpecStore | None:
        return self._agent_spec_store

    def admin_audit_store(self) -> FakeAdminAuditStore | None:
        return self._admin_audit_store


class FakeAgentSpecStore:
    def __init__(self) -> None:
        self.records: dict[str, AgentSpecRecord] = {}

    async def list(self) -> list[AgentSpecRecord]:
        return list(self.records.values())

    async def list_enabled(self) -> list[AgentSpecRecord]:
        return [record for record in self.records.values() if record.enabled]

    async def get(self, spec_id: str) -> AgentSpecRecord | None:
        return self.records.get(spec_id)

    async def save(self, record: AgentSpecRecord) -> AgentSpecRecord:
        record.validate()
        if record.created_at.tzinfo is None:
            record = AgentSpecRecord(
                id=record.id,
                name=record.name,
                description=record.description,
                tool_names=record.tool_names,
                keywords=record.keywords,
                system_prompt=record.system_prompt,
                mode=record.mode,
                independent_execution=record.independent_execution,
                enabled=record.enabled,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        self.records[record.id] = record
        return record

    async def delete(self, spec_id: str) -> None:
        self.records.pop(spec_id, None)


class FakeAdminAuditStore:
    def __init__(self) -> None:
        self.saved: list[AdminAuditLog] = []

    async def save(self, log: AdminAuditLog, *, tenant_id: str = "local") -> AdminAuditLog:
        del tenant_id
        self.saved.append(log)
        return log
