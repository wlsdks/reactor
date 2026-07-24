from __future__ import annotations

from datetime import UTC, datetime

from httpx import ASGITransport, AsyncClient

from reactor.admin.audit import AdminAuditAction, AdminAuditLog
from reactor.api.app import create_app
from reactor.auth.models import UserRecord
from reactor.auth.rbac import UserRole
from reactor.core.settings import Settings

TEST_AUTH_DIGEST = "argon2id$test-digest"


async def test_rbac_roles_requires_developer_admin() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/v1/admin/rbac/roles",
            headers={"X-Reactor-Role": "ADMIN_MANAGER", "X-Reactor-User-Id": "manager_1"},
        )

    assert response.status_code == 403
    body = response.json()
    assert body["detail"] == "admin access required"
    assert body["error"] == "admin access required"
    assert body["statusCode"] == 403
    assert body["code"] == "forbidden"


async def test_rbac_roles_returns_backup_permission_matrix() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/api/admin/rbac/roles",
            headers={"X-Reactor-Role": "ADMIN", "X-Reactor-User-Id": "admin_1"},
        )

    assert response.status_code == 200
    roles = {item["role"]: item for item in response.json()}
    assert roles["ADMIN"]["scope"] == "FULL"
    assert "settings:write" in roles["ADMIN"]["permissions"]
    assert roles["ADMIN_DEVELOPER"]["scope"] == "DEVELOPER"
    assert "agent-spec:write" in roles["ADMIN_DEVELOPER"]["permissions"]
    assert roles["ADMIN_MANAGER"]["scope"] == "MANAGER"
    assert "settings:read" not in roles["ADMIN_MANAGER"]["permissions"]
    assert roles["USER"]["scope"] is None


async def test_rbac_user_role_update_ports_legacy_contract_and_audit() -> None:
    users = FakeUserStore()
    audits = FakeAdminAuditStore()
    await users.save(
        UserRecord(
            id="user_1",
            email="user@example.com",
            name="User One",
            password_hash=TEST_AUTH_DIGEST,
            role=UserRole.USER,
            tenant_id="tenant_1",
            created_at=datetime(2026, 6, 26, 1, 0, tzinfo=UTC),
        )
    )
    app = create_app()
    app.state.reactor = FakeContainer(user_store=users, admin_audit_store=audits)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.put(
            "/api/admin/rbac/users/user_1/role",
            headers={"X-Reactor-Role": "ADMIN_MANAGER", "X-Reactor-User-Id": "manager_1"},
            json={"role": "ADMIN"},
        )
        invalid_role = await client.put(
            "/api/admin/rbac/users/user_1/role",
            headers={"X-Reactor-Role": "ADMIN", "X-Reactor-User-Id": "admin_1"},
            json={"role": "SUPER_ADMIN"},
        )
        lower_role = await client.put(
            "/api/admin/rbac/users/user_1/role",
            headers={"X-Reactor-Role": "ADMIN", "X-Reactor-User-Id": "admin_1"},
            json={"role": "admin"},
        )
        padded_role = await client.put(
            "/api/admin/rbac/users/user_1/role",
            headers={"X-Reactor-Role": "ADMIN", "X-Reactor-User-Id": "admin_1"},
            json={"role": " ADMIN "},
        )
        missing = await client.put(
            "/v1/admin/rbac/users/missing/role",
            headers={"X-Reactor-Role": "ADMIN", "X-Reactor-User-Id": "admin_1"},
            json={"role": "ADMIN"},
        )
        updated = await client.put(
            "/v1/admin/rbac/users/user_1/role",
            headers={"X-Reactor-Role": "ADMIN", "X-Reactor-User-Id": "admin_1"},
            json={"role": "ADMIN_MANAGER"},
        )

    assert forbidden.status_code == 403
    assert forbidden.json()["error"] == "관리자 권한이 필요합니다"
    assert "timestamp" in forbidden.json()
    assert invalid_role.status_code == 400
    assert invalid_role.json()["error"] == "유효하지 않은 역할: SUPER_ADMIN"
    assert lower_role.status_code == 400
    assert lower_role.json()["error"] == "유효하지 않은 역할: admin"
    assert padded_role.status_code == 400
    assert padded_role.json()["error"] == "유효하지 않은 역할:  ADMIN "
    assert missing.status_code == 404
    assert missing.json()["error"] == "사용자를 찾을 수 없습니다: missing"
    assert updated.status_code == 200
    assert updated.json() == {"userId": "user_1", "role": "ADMIN_MANAGER"}
    user = await users.find_by_id("user_1")
    assert user is not None
    assert user.role == UserRole.ADMIN_MANAGER
    assert audits.saved[-1].category == "rbac"
    assert audits.saved[-1].action == AdminAuditAction.UPDATE_ROLE
    assert audits.saved[-1].actor == "admin_1"
    assert audits.saved[-1].resource_type == "user"
    assert audits.saved[-1].resource_id == "user_1"
    assert audits.saved[-1].detail == "role=ADMIN_MANAGER"


async def test_rbac_user_role_update_returns_not_found_for_unknown_local_user() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.put(
            "/api/admin/rbac/users/user_1/role",
            headers={"X-Reactor-Role": "ADMIN", "X-Reactor-User-Id": "admin_1"},
            json={"role": "ADMIN"},
        )

    assert response.status_code == 404
    assert response.json()["error"] == "사용자를 찾을 수 없습니다: user_1"


class FakeContainer:
    def __init__(
        self,
        *,
        user_store: FakeUserStore | None = None,
        admin_audit_store: FakeAdminAuditStore | None = None,
    ) -> None:
        self.settings = Settings()
        self._user_store = user_store
        self._admin_audit_store = admin_audit_store

    def user_store(self) -> FakeUserStore | None:
        return self._user_store

    def admin_audit_store(self) -> FakeAdminAuditStore | None:
        return self._admin_audit_store


class FakeUserStore:
    def __init__(self) -> None:
        self.users_by_id: dict[str, UserRecord] = {}

    async def find_by_id(self, user_id: str) -> UserRecord | None:
        return self.users_by_id.get(user_id)

    async def save(self, user: UserRecord) -> UserRecord:
        self.users_by_id[user.id] = user
        return user

    async def update(self, user: UserRecord) -> UserRecord:
        return await self.save(user)


class FakeAdminAuditStore:
    def __init__(self) -> None:
        self.saved: list[AdminAuditLog] = []

    async def save(self, log: AdminAuditLog, *, tenant_id: str = "tenant_1") -> AdminAuditLog:
        del tenant_id
        self.saved.append(log)
        return log
