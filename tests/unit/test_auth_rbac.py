from __future__ import annotations

from reactor.auth.rbac import (
    ANONYMOUS_USER_ID,
    AdminScope,
    AuthPrincipal,
    UserRole,
    current_actor,
    masked_admin_account_ref,
    parse_role,
    permissions_for,
    role_definitions,
)


def test_user_role_admin_scope_matches_backup_contract() -> None:
    assert UserRole.ADMIN.is_developer_admin() is True
    assert UserRole.ADMIN_DEVELOPER.is_developer_admin() is True
    assert UserRole.ADMIN_MANAGER.is_developer_admin() is False
    assert UserRole.USER.is_developer_admin() is False

    assert UserRole.ADMIN.is_any_admin() is True
    assert UserRole.ADMIN_MANAGER.is_any_admin() is True
    assert UserRole.ADMIN_DEVELOPER.is_any_admin() is True
    assert UserRole.USER.is_any_admin() is False

    assert UserRole.ADMIN.admin_scope() == AdminScope.FULL
    assert UserRole.ADMIN_MANAGER.admin_scope() == AdminScope.MANAGER
    assert UserRole.ADMIN_DEVELOPER.admin_scope() == AdminScope.DEVELOPER
    assert UserRole.USER.admin_scope() is None


def test_role_permissions_match_rbac_controller_matrix_for_settings() -> None:
    assert "settings:read" in permissions_for(UserRole.ADMIN)
    assert "settings:write" in permissions_for(UserRole.ADMIN)
    assert "settings:read" not in permissions_for(UserRole.ADMIN_DEVELOPER)
    assert "settings:write" not in permissions_for(UserRole.ADMIN_DEVELOPER)
    assert "settings:read" not in permissions_for(UserRole.ADMIN_MANAGER)
    assert "settings:write" not in permissions_for(UserRole.USER)


def test_role_definitions_include_scope_and_permissions() -> None:
    definitions = {definition.role: definition for definition in role_definitions()}

    assert definitions[UserRole.ADMIN].scope == AdminScope.FULL
    assert "agent-spec:write" in definitions[UserRole.ADMIN_DEVELOPER].permissions
    assert definitions[UserRole.USER].scope is None


def test_parse_role_fails_closed_to_user() -> None:
    assert parse_role("ADMIN") == UserRole.ADMIN
    assert parse_role("admin_developer") == UserRole.ADMIN_DEVELOPER
    assert parse_role("bad") == UserRole.USER
    assert parse_role(None) == UserRole.USER


def test_current_actor_and_masked_admin_reference() -> None:
    principal = AuthPrincipal(user_id="admin_1", tenant_id="tenant_1", role=UserRole.ADMIN)

    assert current_actor(principal) == "admin_1"
    assert current_actor(None) == ANONYMOUS_USER_ID
    assert masked_admin_account_ref("admin_1").startswith("admin-account:")
    assert masked_admin_account_ref(None) == "admin-account:unknown"
