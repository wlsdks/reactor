from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256

ANONYMOUS_USER_ID = "anonymous"


class AdminScope(StrEnum):
    FULL = "FULL"
    MANAGER = "MANAGER"
    DEVELOPER = "DEVELOPER"


class UserRole(StrEnum):
    USER = "USER"
    ADMIN = "ADMIN"
    ADMIN_MANAGER = "ADMIN_MANAGER"
    ADMIN_DEVELOPER = "ADMIN_DEVELOPER"

    def is_any_admin(self) -> bool:
        return self in {UserRole.ADMIN, UserRole.ADMIN_MANAGER, UserRole.ADMIN_DEVELOPER}

    def is_developer_admin(self) -> bool:
        return self in {UserRole.ADMIN, UserRole.ADMIN_DEVELOPER}

    def admin_scope(self) -> AdminScope | None:
        match self:
            case UserRole.ADMIN:
                return AdminScope.FULL
            case UserRole.ADMIN_MANAGER:
                return AdminScope.MANAGER
            case UserRole.ADMIN_DEVELOPER:
                return AdminScope.DEVELOPER
            case UserRole.USER:
                return None


@dataclass(frozen=True)
class AuthPrincipal:
    user_id: str
    tenant_id: str
    role: UserRole
    groups: tuple[str, ...] = ()

    def is_any_admin(self) -> bool:
        return self.role.is_any_admin()

    def is_developer_admin(self) -> bool:
        return self.role.is_developer_admin()

    def has_permission(self, permission: str) -> bool:
        return permission in permissions_for(self.role)


@dataclass(frozen=True)
class RoleDefinition:
    role: UserRole
    scope: AdminScope | None
    permissions: tuple[str, ...]


def parse_role(value: str | None) -> UserRole:
    if value is None or not value.strip():
        return UserRole.USER
    normalized = value.strip().upper()
    try:
        return UserRole(normalized)
    except ValueError:
        return UserRole.USER


def parse_groups(value: str | None) -> tuple[str, ...]:
    if value is None:
        return ()
    groups: list[str] = []
    seen: set[str] = set()
    for raw_group in value.split(","):
        group = raw_group.strip()
        if not group or group in seen:
            continue
        groups.append(group)
        seen.add(group)
    return tuple(groups)


def current_actor(principal: AuthPrincipal | None) -> str:
    if principal is None or not principal.user_id.strip():
        return ANONYMOUS_USER_ID
    return principal.user_id


def masked_admin_account_ref(actor: str | None) -> str:
    normalized = actor.strip() if actor is not None else ""
    if not normalized:
        return "admin-account:unknown"
    if normalized == ANONYMOUS_USER_ID:
        return f"admin-account:{ANONYMOUS_USER_ID}"
    return f"admin-account:{sha256(normalized.encode()).hexdigest()[:12]}"


def permissions_for(role: UserRole) -> tuple[str, ...]:
    match role:
        case UserRole.ADMIN:
            return (
                "persona:read",
                "persona:write",
                "prompt:read",
                "prompt:write",
                "session:read",
                "session:export",
                "feedback:read",
                "guard:read",
                "guard:write",
                "mcp:read",
                "mcp:write",
                "scheduler:read",
                "scheduler:write",
                "eval:read",
                "eval:write",
                "audit:read",
                "audit:export",
                "tenant:read",
                "tenant:write",
                "tenant:export",
                "user:read",
                "user:write",
                "settings:read",
                "settings:write",
                "slack:write",
                "agent-spec:read",
                "agent-spec:write",
            )
        case UserRole.ADMIN_DEVELOPER:
            return (
                "persona:read",
                "persona:write",
                "prompt:read",
                "prompt:write",
                "session:read",
                "feedback:read",
                "guard:read",
                "guard:write",
                "mcp:read",
                "mcp:write",
                "scheduler:read",
                "scheduler:write",
                "audit:read",
                "agent-spec:read",
                "agent-spec:write",
            )
        case UserRole.ADMIN_MANAGER:
            return (
                "session:read",
                "session:export",
                "feedback:read",
                "audit:read",
                "persona:read",
            )
        case UserRole.USER:
            return ("chat:use", "persona:select")


def role_definitions() -> tuple[RoleDefinition, ...]:
    return tuple(
        RoleDefinition(
            role=role,
            scope=role.admin_scope(),
            permissions=permissions_for(role),
        )
        for role in UserRole
    )
