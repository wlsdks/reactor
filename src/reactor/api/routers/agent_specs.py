from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Protocol, cast

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import JSONResponse

from reactor.admin.audit import AdminAuditAction, AdminAuditLog
from reactor.agents.specs import (
    AgentSpecRecord,
    parse_agent_spec_mode,
    system_prompt_preview,
)
from reactor.api.auth import principal_from_headers
from reactor.api.schemas.agent_specs import (
    AgentSpecResponse,
    AgentSpecSystemPromptResponse,
    CreateAgentSpecRequest,
    UpdateAgentSpecRequest,
)
from reactor.auth.rbac import AuthPrincipal, current_actor
from reactor.core.container import AppContainer

router = APIRouter(tags=["agent-specs"])


class AgentSpecStore(Protocol):
    async def list(self) -> list[AgentSpecRecord]: ...

    async def list_enabled(self) -> list[AgentSpecRecord]: ...

    async def get(self, spec_id: str) -> AgentSpecRecord | None: ...

    async def save(self, record: AgentSpecRecord) -> AgentSpecRecord: ...

    async def delete(self, spec_id: str) -> None: ...


@router.get(
    "/api/admin/agent-specs",
    response_model=list[AgentSpecResponse],
    response_model_by_alias=True,
)
@router.get(
    "/v1/admin/agent-specs",
    response_model=list[AgentSpecResponse],
    response_model_by_alias=True,
)
async def list_agent_specs(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(principal_from_headers)],
    enabled: bool | None = None,
) -> list[AgentSpecResponse] | JSONResponse:
    permission_error = require_agent_spec_permission(principal, "agent-spec:read")
    if permission_error is not None:
        return permission_error
    store = require_agent_spec_store(request)
    if isinstance(store, JSONResponse):
        return store
    records = await store.list_enabled() if enabled is True else await store.list()
    return [agent_spec_response(record) for record in records]


@router.get(
    "/api/admin/agent-specs/{spec_id}",
    response_model=AgentSpecResponse,
    response_model_by_alias=True,
)
@router.get(
    "/v1/admin/agent-specs/{spec_id}",
    response_model=AgentSpecResponse,
    response_model_by_alias=True,
)
async def get_agent_spec(
    request: Request,
    spec_id: str,
    principal: Annotated[AuthPrincipal, Depends(principal_from_headers)],
) -> AgentSpecResponse | JSONResponse:
    permission_error = require_agent_spec_permission(principal, "agent-spec:read")
    if permission_error is not None:
        return permission_error
    store = require_agent_spec_store(request)
    if isinstance(store, JSONResponse):
        return store
    record = await store.get(spec_id)
    if record is None:
        return agent_spec_not_found(spec_id)
    return agent_spec_response(record)


@router.post(
    "/api/admin/agent-specs",
    response_model=AgentSpecResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/v1/admin/agent-specs",
    response_model=AgentSpecResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
async def create_agent_spec(
    request: Request,
    body: CreateAgentSpecRequest,
    principal: Annotated[AuthPrincipal, Depends(principal_from_headers)],
) -> AgentSpecResponse | JSONResponse:
    permission_error = require_agent_spec_permission(principal, "agent-spec:write")
    if permission_error is not None:
        return permission_error
    mode = parse_agent_spec_mode(body.mode)
    if mode is None:
        return legacy_error_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            error=f"유효하지 않은 모드: {body.mode}",
        )
    store = require_agent_spec_store(request)
    if isinstance(store, JSONResponse):
        return store
    if any(record.name == body.name for record in await store.list()):
        return legacy_error_response(
            status_code=status.HTTP_409_CONFLICT,
            error=f"이름 '{body.name}'은 이미 사용 중입니다",
        )
    saved = await store.save(
        AgentSpecRecord(
            name=body.name,
            description=body.description or "",
            tool_names=body.toolNames or (),
            keywords=body.keywords or (),
            system_prompt=body.systemPrompt,
            mode=mode,
            independent_execution=body.independentExecution
            if body.independentExecution is not None
            else True,
            enabled=body.enabled if body.enabled is not None else True,
        )
    )
    await record_agent_spec_audit(
        request=request,
        principal=principal,
        action=AdminAuditAction.CREATE,
        record=saved,
    )
    return agent_spec_response(saved)


@router.put(
    "/api/admin/agent-specs/{spec_id}",
    response_model=AgentSpecResponse,
    response_model_by_alias=True,
)
@router.put(
    "/v1/admin/agent-specs/{spec_id}",
    response_model=AgentSpecResponse,
    response_model_by_alias=True,
)
async def update_agent_spec(
    request: Request,
    spec_id: str,
    body: UpdateAgentSpecRequest,
    principal: Annotated[AuthPrincipal, Depends(principal_from_headers)],
) -> AgentSpecResponse | JSONResponse:
    permission_error = require_agent_spec_permission(principal, "agent-spec:write")
    if permission_error is not None:
        return permission_error
    mode = parse_agent_spec_mode(body.mode) if body.mode is not None else None
    if body.mode is not None and mode is None:
        return legacy_error_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            error=f"유효하지 않은 모드: {body.mode}",
        )
    store = require_agent_spec_store(request)
    if isinstance(store, JSONResponse):
        return store
    existing = await store.get(spec_id)
    if existing is None:
        return agent_spec_not_found(spec_id)
    if body.name is not None and body.name != existing.name:
        for record in await store.list():
            if record.id != spec_id and record.name == body.name:
                return duplicate_agent_spec_name(body.name)
    saved = await store.save(
        existing.with_updates(
            name=body.name,
            description=body.description,
            tool_names=body.toolNames,
            keywords=body.keywords,
            system_prompt=body.systemPrompt,
            mode=mode,
            independent_execution=body.independentExecution,
            enabled=body.enabled,
        )
    )
    await record_agent_spec_audit(
        request=request,
        principal=principal,
        action=AdminAuditAction.UPDATE,
        record=saved,
    )
    return agent_spec_response(saved)


@router.get(
    "/api/admin/agent-specs/{spec_id}/system-prompt",
    response_model=AgentSpecSystemPromptResponse,
    response_model_by_alias=True,
)
@router.get(
    "/v1/admin/agent-specs/{spec_id}/system-prompt",
    response_model=AgentSpecSystemPromptResponse,
    response_model_by_alias=True,
)
async def get_agent_spec_system_prompt(
    request: Request,
    spec_id: str,
    principal: Annotated[AuthPrincipal, Depends(principal_from_headers)],
) -> AgentSpecSystemPromptResponse | JSONResponse:
    permission_error = require_agent_spec_permission(principal, "agent-spec:read")
    if permission_error is not None:
        return permission_error
    store = require_agent_spec_store(request)
    if isinstance(store, JSONResponse):
        return store
    record = await store.get(spec_id)
    if record is None:
        return agent_spec_not_found(spec_id)
    await record_agent_spec_system_prompt_read(
        request=request,
        principal=principal,
        record=record,
    )
    return AgentSpecSystemPromptResponse(systemPrompt=record.system_prompt)


@router.delete(
    "/api/admin/agent-specs/{spec_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
@router.delete(
    "/v1/admin/agent-specs/{spec_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_agent_spec(
    request: Request,
    spec_id: str,
    principal: Annotated[AuthPrincipal, Depends(principal_from_headers)],
) -> Response | JSONResponse:
    permission_error = require_agent_spec_permission(principal, "agent-spec:write")
    if permission_error is not None:
        return permission_error
    store = require_agent_spec_store(request)
    if isinstance(store, JSONResponse):
        return store
    record = await store.get(spec_id)
    if record is None:
        return agent_spec_not_found(spec_id)
    await store.delete(spec_id)
    await record_admin_audit_if_configured(
        request=request,
        principal=principal,
        category="agent_spec",
        action=AdminAuditAction.DELETE,
        resource_type="agent_spec",
        resource_id=spec_id,
        detail=None,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def get_container(request: Request) -> AppContainer:
    return cast(AppContainer, request.app.state.reactor)


def require_agent_spec_permission(
    principal: AuthPrincipal,
    permission: str,
) -> JSONResponse | None:
    if principal.has_permission(permission):
        return None
    return legacy_error_response(
        status_code=status.HTTP_403_FORBIDDEN,
        error="관리자 권한이 필요합니다",
    )


def require_agent_spec_store(request: Request) -> AgentSpecStore | JSONResponse:
    container = get_container(request)
    accessor = getattr(container, "agent_spec_store", None)
    store = accessor() if accessor is not None else None
    if store is None:
        return legacy_error_response(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            error="AgentSpecStore 미등록 — DB 미구성",
        )
    return cast(AgentSpecStore, store)


def admin_audit_store(request: Request):
    container = get_container(request)
    accessor = getattr(container, "admin_audit_store", None)
    return accessor() if accessor is not None else None


async def record_agent_spec_audit(
    *,
    request: Request,
    principal: AuthPrincipal,
    action: AdminAuditAction,
    record: AgentSpecRecord,
) -> None:
    await record_admin_audit_if_configured(
        request=request,
        principal=principal,
        category="agent_spec",
        action=action,
        resource_type="agent_spec",
        resource_id=record.id,
        detail=f"name={record.name}",
    )


async def record_agent_spec_system_prompt_read(
    *,
    request: Request,
    principal: AuthPrincipal,
    record: AgentSpecRecord,
) -> None:
    await record_admin_audit_if_configured(
        request=request,
        principal=principal,
        category="agent_spec",
        action=AdminAuditAction.READ,
        resource_type="agent_spec_system_prompt",
        resource_id=record.id,
        detail=f"name={record.name}",
    )


async def record_admin_audit_if_configured(
    *,
    request: Request,
    principal: AuthPrincipal,
    category: str,
    action: AdminAuditAction,
    resource_type: str,
    resource_id: str,
    detail: str | None,
) -> None:
    store = admin_audit_store(request)
    if store is None:
        return
    await store.save(
        AdminAuditLog(
            category=category,
            action=action,
            actor=current_actor(principal),
            resource_type=resource_type,
            resource_id=resource_id,
            detail=detail,
        ),
        tenant_id=principal.tenant_id,
    )


def agent_spec_not_found(spec_id: str) -> JSONResponse:
    return legacy_error_response(
        status_code=status.HTTP_404_NOT_FOUND,
        error=f"에이전트 스펙을 찾을 수 없습니다: {spec_id}",
    )


def duplicate_agent_spec_name(name: str) -> JSONResponse:
    return legacy_error_response(
        status_code=status.HTTP_409_CONFLICT,
        error=f"이름 '{name}'은 이미 사용 중입니다",
    )


def legacy_error_response(*, status_code: int, error: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": error,
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )


def agent_spec_response(record: AgentSpecRecord) -> AgentSpecResponse:
    prompt = record.system_prompt if record.system_prompt and record.system_prompt.strip() else None
    return AgentSpecResponse(
        id=record.id,
        name=record.name,
        description=record.description,
        toolNames=record.tool_names,
        keywords=record.keywords,
        systemPromptPreview=system_prompt_preview(record.system_prompt),
        hasSystemPrompt=prompt is not None,
        mode=record.mode.value,
        independentExecution=record.independent_execution,
        enabled=record.enabled,
        createdAt=record.created_at.isoformat(),
        updatedAt=record.updated_at.isoformat(),
    )
