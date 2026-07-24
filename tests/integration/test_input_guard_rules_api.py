from __future__ import annotations

from httpx import ASGITransport, AsyncClient

from reactor.api.app import create_app
from reactor.core.settings import Settings
from reactor.guards.rules import InputGuardRuleRecord

ADMIN_HEADERS = {
    "X-Reactor-User-Id": "admin_1",
    "X-Reactor-Tenant-Id": "tenant_1",
    "X-Reactor-Role": "ADMIN",
}


async def test_input_guard_rules_require_admin_and_persistence() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.get("/api/admin/input-guard/rules")
        unavailable = await client.get("/api/admin/input-guard/rules", headers=ADMIN_HEADERS)

    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == "permission required: guard:read"
    assert unavailable.status_code == 503
    assert unavailable.json()["detail"] == "input guard rule persistence is not configured"


async def test_input_guard_rule_crud_flow() -> None:
    store = FakeInputGuardRuleStore()
    app = create_app()
    app.state.reactor = FakeContainer(store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        created = await client.post(
            "/api/admin/input-guard/rules",
            headers=ADMIN_HEADERS,
            json={
                "name": "Block jailbreak",
                "pattern": "ignore previous",
                "patternType": "keyword",
                "action": "block",
                "priority": 500,
                "category": "jailbreak",
            },
        )
        rule_id = created.json()["id"]
        listed = await client.get("/v1/admin/input-guard/rules", headers=ADMIN_HEADERS)
        fetched = await client.get(f"/api/admin/input-guard/rules/{rule_id}", headers=ADMIN_HEADERS)
        updated = await client.put(
            f"/v1/admin/input-guard/rules/{rule_id}",
            headers=ADMIN_HEADERS,
            json={
                "name": "Warn jailbreak",
                "pattern": "ignore previous",
                "patternType": "keyword",
                "action": "warn",
                "priority": 600,
                "category": "jailbreak",
                "enabled": False,
            },
        )
        deleted = await client.delete(
            f"/api/admin/input-guard/rules/{rule_id}", headers=ADMIN_HEADERS
        )

    assert created.status_code == 200
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Block jailbreak"
    assert updated.status_code == 200
    assert updated.json()["action"] == "warn"
    assert updated.json()["enabled"] is False
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True, "id": rule_id}


async def test_input_guard_rule_validation_rejects_bad_pattern_type_action_and_regex() -> None:
    app = create_app()
    app.state.reactor = FakeContainer(FakeInputGuardRuleStore())
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        bad_pattern_type = await client.post(
            "/api/admin/input-guard/rules",
            headers=ADMIN_HEADERS,
            json={"name": "bad", "pattern": "x", "patternType": "glob", "action": "block"},
        )
        bad_action = await client.post(
            "/api/admin/input-guard/rules",
            headers=ADMIN_HEADERS,
            json={"name": "bad", "pattern": "x", "patternType": "keyword", "action": "drop"},
        )
        bad_regex = await client.post(
            "/api/admin/input-guard/rules",
            headers=ADMIN_HEADERS,
            json={"name": "bad", "pattern": "[", "patternType": "regex", "action": "block"},
        )

    assert bad_pattern_type.status_code == 400
    assert bad_pattern_type.json()["detail"] == "patternType must be regex or keyword"
    assert bad_action.status_code == 400
    assert bad_action.json()["detail"] == "action must be block, warn, or flag"
    assert bad_regex.status_code == 400
    assert bad_regex.json()["detail"] == "invalid regex pattern"


class FakeContainer:
    def __init__(self, store: FakeInputGuardRuleStore) -> None:
        self.settings = Settings()
        self._store = store

    def input_guard_rule_store(self) -> FakeInputGuardRuleStore:
        return self._store


class FakeInputGuardRuleStore:
    def __init__(self) -> None:
        self.rules: dict[str, InputGuardRuleRecord] = {}

    async def find_all(self, *, tenant_id: str) -> list[InputGuardRuleRecord]:
        return [rule for rule in self.rules.values() if rule.tenant_id == tenant_id]

    async def find_by_id(self, *, tenant_id: str, rule_id: str) -> InputGuardRuleRecord | None:
        rule = self.rules.get(rule_id)
        return rule if rule is not None and rule.tenant_id == tenant_id else None

    async def save(self, rule: InputGuardRuleRecord) -> InputGuardRuleRecord:
        rule.validate()
        self.rules[rule.id] = rule
        return rule

    async def update(
        self,
        *,
        tenant_id: str,
        rule_id: str,
        rule: InputGuardRuleRecord,
    ) -> InputGuardRuleRecord | None:
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
