from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from reactor.admin.audit import AdminAuditAction, AdminAuditLog
from reactor.api.auth import principal_from_headers, require_developer_admin
from reactor.api.schemas.rbac import (
    RoleDefinitionResponse,
    UpdateRoleRequest,
    UpdateRoleResponse,
)
from reactor.auth.models import UserRecord
from reactor.auth.rbac import AuthPrincipal, UserRole, current_actor, role_definitions
from reactor.core.container import AppContainer

router = APIRouter(tags=["rbac"])


@router.get("/v1/admin/rbac/roles", response_model=list[RoleDefinitionResponse])
@router.get("/api/admin/rbac/roles", response_model=list[RoleDefinitionResponse])
async def list_roles(
    _: Annotated[AuthPrincipal, Depends(require_developer_admin)],
) -> list[RoleDefinitionResponse]:
    return [
        RoleDefinitionResponse(
            role=definition.role.value,
            scope=definition.scope.value if definition.scope is not None else None,
            permissions=list(definition.permissions),
        )
        for definition in role_definitions()
    ]


@router.put(
    "/v1/admin/rbac/users/{user_id}/role",
    response_model=UpdateRoleResponse,
    response_model_by_alias=True,
)
@router.put(
    "/api/admin/rbac/users/{user_id}/role",
    response_model=UpdateRoleResponse,
    response_model_by_alias=True,
)
async def update_user_role(
    request: Request,
    user_id: str,
    body: UpdateRoleRequest,
    principal: Annotated[AuthPrincipal, Depends(principal_from_headers)],
) -> UpdateRoleResponse | JSONResponse:
    if not principal.has_permission("user:write"):
        return legacy_error_response(
            status_code=status.HTTP_403_FORBIDDEN,
            error="관리자 권한이 필요합니다",
        )
    next_role = parse_body_role(body.role)
    if next_role is None:
        return legacy_error_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            error=f"유효하지 않은 역할: {body.role}",
        )
    store = require_user_store(request)
    user = await store.find_by_id(user_id)
    if user is None:
        return legacy_error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            error=f"사용자를 찾을 수 없습니다: {user_id}",
        )
    await store.update(
        UserRecord(
            id=user.id,
            email=user.email,
            name=user.name,
            password_hash=user.password_hash,
            role=next_role,
            tenant_id=user.tenant_id,
            created_at=user.created_at,
        )
    )
    await record_rbac_role_update_audit(
        request=request,
        principal=principal,
        user_id=user_id,
        role=next_role,
    )
    return UpdateRoleResponse(userId=user_id, role=next_role.value)


def parse_body_role(value: str) -> UserRole | None:
    try:
        return UserRole(value)
    except ValueError:
        return None


def legacy_error_response(*, status_code: int, error: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": error,
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )


def get_container(request: Request) -> AppContainer:
    return cast(AppContainer, request.app.state.reactor)


def require_user_store(request: Request):
    container = get_container(request)
    accessor = getattr(container, "user_store", None)
    store = accessor() if accessor is not None else None
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="user persistence is not configured",
        )
    return store


def admin_audit_store(request: Request):
    container = get_container(request)
    accessor = getattr(container, "admin_audit_store", None)
    return accessor() if accessor is not None else None


async def record_rbac_role_update_audit(
    *,
    request: Request,
    principal: AuthPrincipal,
    user_id: str,
    role: UserRole,
) -> None:
    store = admin_audit_store(request)
    if store is None:
        return
    await store.save(
        AdminAuditLog(
            category="rbac",
            action=AdminAuditAction.UPDATE_ROLE,
            actor=current_actor(principal),
            resource_type="user",
            resource_id=user_id,
            detail=f"role={role.value}",
        ),
        tenant_id=principal.tenant_id,
    )
