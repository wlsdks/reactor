from __future__ import annotations

from httpx import ASGITransport, AsyncClient

from reactor.api.app import create_app
from reactor.core.settings import Settings
from reactor.guards.output_rules import (
    OutputGuardRuleAuditRecord,
    OutputGuardRuleRecord,
)

ADMIN_HEADERS = {
    "X-Reactor-User-Id": "admin_1",
    "X-Reactor-Tenant-Id": "tenant_1",
    "X-Reactor-Role": "ADMIN",
}

MANAGER_HEADERS = {
    "X-Reactor-User-Id": "manager_1",
    "X-Reactor-Tenant-Id": "tenant_1",
    "X-Reactor-Role": "ADMIN_MANAGER",
}


async def test_output_guard_rules_require_developer_admin_and_persistence() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.get("/api/output-guard/rules", headers=MANAGER_HEADERS)
        unavailable = await client.get("/api/output-guard/rules", headers=ADMIN_HEADERS)

    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == "permission required: guard:read"
    assert unavailable.status_code == 503
    assert unavailable.json()["detail"] == "output guard rule persistence is not configured"


async def test_output_guard_rules_dynamic_disable_uses_legacy_error_body() -> None:
    app = create_app()
    app.state.reactor = FakeContainer(
        FakeOutputGuardRuleStore(),
        FakeOutputGuardRuleAuditStore(),
        settings=Settings(output_guard_dynamic_rules_enabled=False),
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/output-guard/rules", headers=ADMIN_HEADERS)

    assert response.status_code == 503
    assert response.json() == {"error": "Dynamic output guard rules are disabled"}


async def test_output_guard_rule_crud_audit_and_simulation_flow() -> None:
    rule_store = FakeOutputGuardRuleStore()
    audit_store = FakeOutputGuardRuleAuditStore()
    app = create_app()
    app.state.reactor = FakeContainer(rule_store, audit_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        created_mask = await client.post(
            "/api/output-guard/rules",
            headers=ADMIN_HEADERS,
            json={
                "name": "Mask token",
                "pattern": "token-[0-9]+",
                "action": "mask",
                "replacement": "[TOKEN]",
                "priority": 10,
            },
        )
        created_reject = await client.post(
            "/v1/output-guard/rules",
            headers=ADMIN_HEADERS,
            json={
                "name": "Reject canary",
                "pattern": "never-send",
                "action": "REJECT",
                "priority": 1,
                "enabled": False,
            },
        )
        mask_id = created_mask.json()["id"]
        reject_id = created_reject.json()["id"]
        listed = await client.get("/api/output-guard/rules", headers=ADMIN_HEADERS)
        updated_reject = await client.put(
            f"/api/output-guard/rules/{reject_id}",
            headers=ADMIN_HEADERS,
            json={"enabled": True, "priority": 20},
        )
        simulated = await client.post(
            "/v1/output-guard/rules/simulate",
            headers=ADMIN_HEADERS,
            json={"content": "token-123 never-send"},
        )
        audits = await client.get("/api/output-guard/rules/audits?limit=10", headers=ADMIN_HEADERS)
        deleted = await client.delete(
            f"/v1/output-guard/rules/{mask_id}",
            headers=ADMIN_HEADERS,
        )

    assert created_mask.status_code == 201
    assert created_mask.json()["action"] == "MASK"
    assert created_reject.status_code == 201
    assert listed.status_code == 200
    assert [rule["id"] for rule in listed.json()] == [reject_id, mask_id]
    assert updated_reject.status_code == 200
    assert updated_reject.json()["enabled"] is True
    assert simulated.status_code == 200
    assert simulated.json()["resultContent"] == "[TOKEN] never-send"
    assert simulated.json()["blocked"] is True
    assert simulated.json()["blockedByRuleId"] == reject_id
    assert [match["ruleId"] for match in simulated.json()["matchedRules"]] == [
        mask_id,
        reject_id,
    ]
    assert audits.status_code == 200
    assert audits.json()[0]["action"] == "SIMULATE"
    assert audits.json()[0]["actor"].startswith("admin-account:")
    assert deleted.status_code == 204


async def test_output_guard_rule_validation_rejects_invalid_action_and_regex() -> None:
    app = create_app()
    app.state.reactor = FakeContainer(FakeOutputGuardRuleStore(), FakeOutputGuardRuleAuditStore())
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        bad_action = await client.post(
            "/api/output-guard/rules",
            headers=ADMIN_HEADERS,
            json={"name": "bad", "pattern": "x", "action": "BLOCK"},
        )
        bad_regex = await client.post(
            "/api/output-guard/rules",
            headers=ADMIN_HEADERS,
            json={"name": "bad", "pattern": "[", "action": "MASK"},
        )

    assert bad_action.status_code == 400
    assert bad_action.json()["detail"] == "Invalid action: BLOCK"
    assert bad_regex.status_code == 400
    assert bad_regex.json()["detail"] == "Invalid pattern: invalid regex pattern"


class FakeContainer:
    def __init__(
        self,
        rule_store: FakeOutputGuardRuleStore,
        audit_store: FakeOutputGuardRuleAuditStore,
        *,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self._rule_store = rule_store
        self._audit_store = audit_store

    def output_guard_rule_store(self) -> FakeOutputGuardRuleStore:
        return self._rule_store

    def output_guard_rule_audit_store(self) -> FakeOutputGuardRuleAuditStore:
        return self._audit_store


class FakeOutputGuardRuleStore:
    def __init__(self) -> None:
        self.rules: dict[str, OutputGuardRuleRecord] = {}

    async def list(
        self, *, tenant_id: str, include_disabled: bool = True
    ) -> list[OutputGuardRuleRecord]:
        rules = [
            rule
            for rule in self.rules.values()
            if rule.tenant_id == tenant_id and (include_disabled or rule.enabled)
        ]
        return sorted(rules, key=lambda rule: (rule.priority, rule.created_at, rule.id))

    async def find_by_id(self, *, tenant_id: str, rule_id: str) -> OutputGuardRuleRecord | None:
        rule = self.rules.get(rule_id)
        return rule if rule is not None and rule.tenant_id == tenant_id else None

    async def save(self, rule: OutputGuardRuleRecord) -> OutputGuardRuleRecord:
        rule.validate()
        self.rules[rule.id] = rule
        return rule

    async def update(
        self,
        *,
        tenant_id: str,
        rule_id: str,
        rule: OutputGuardRuleRecord,
    ) -> OutputGuardRuleRecord | None:
        if rule_id not in self.rules or self.rules[rule_id].tenant_id != tenant_id:
            return None
        rule.validate()
        self.rules[rule_id] = rule
        return rule

    async def delete(self, *, tenant_id: str, rule_id: str) -> bool:
        rule = self.rules.get(rule_id)
        if rule is None or rule.tenant_id != tenant_id:
            return False
        self.rules.pop(rule_id)
        return True


class FakeOutputGuardRuleAuditStore:
    def __init__(self) -> None:
        self.audits: list[OutputGuardRuleAuditRecord] = []

    async def list(self, *, tenant_id: str, limit: int = 100) -> list[OutputGuardRuleAuditRecord]:
        return [audit for audit in self.audits if audit.tenant_id == tenant_id][:limit]

    async def save(self, audit: OutputGuardRuleAuditRecord) -> OutputGuardRuleAuditRecord:
        self.audits.insert(0, audit)
        return audit
