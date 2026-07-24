from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from time import time
from typing import Annotated, Any, Protocol, cast
from urllib.parse import quote, urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from reactor.admin.audit import AdminAuditAction, AdminAuditLog
from reactor.api.auth import require_any_admin
from reactor.api.schemas.mcp_security import (
    McpSecurityPolicyResponse,
    McpSecurityPolicyStateResponse,
    UpdateMcpSecurityPolicyRequest,
)
from reactor.auth.rbac import AuthPrincipal, current_actor
from reactor.core.container import AppContainer
from reactor.kernel.ids import new_id
from reactor.mcp.admin_preflight import (
    ADMIN_PREFLIGHT_PATH,
    admin_preflight_url,
    preflight_config_from_server,
    preflight_hmac_signature,
)
from reactor.mcp.registry import McpServerRegistration
from reactor.mcp.security_policy import (
    McpSecurityPolicy,
    delete_mcp_security_policy,
    epoch_millis,
    load_mcp_security_policy_state,
    save_mcp_security_policy,
)
from reactor.persistence.mcp_store import McpAccessPolicyRecord

router = APIRouter(prefix="/v1/mcp", tags=["mcp"])
legacy_router = APIRouter(tags=["mcp"])


class McpRegistryStore(Protocol):
    async def register_server(self, registration: McpServerRegistration) -> str: ...

    async def list_servers(self, tenant_id: str) -> list[Any]: ...

    async def find_server_by_name(self, *, tenant_id: str, name: str) -> Any | None: ...

    async def update_server(
        self,
        *,
        tenant_id: str,
        name: str,
        registration: McpServerRegistration,
    ) -> Any | None: ...

    async def set_server_status(self, *, tenant_id: str, name: str, status: str) -> Any | None: ...

    async def delete_server(self, *, tenant_id: str, name: str) -> bool: ...

    async def list_access_policies(
        self,
        *,
        tenant_id: str,
        server_id: str,
    ) -> list[Any]: ...

    async def save_access_policy(self, record: McpAccessPolicyRecord) -> McpAccessPolicyRecord: ...

    async def delete_access_policies(self, *, tenant_id: str, server_id: str) -> int: ...


class RegisterMcpServerRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    transport: str
    command: str | None = Field(default=None, max_length=2_000)
    args: list[str] = Field(default_factory=list, max_length=100)
    url: str | None = Field(default=None, max_length=2_000)
    auth_type: str = Field(default="none", max_length=32)
    timeout_ms: int = Field(default=15_000, gt=0, le=300_000)
    reconnect_policy: dict[str, object] = Field(default_factory=dict)


class UpdateMcpServerRequest(BaseModel):
    transport: str | None = None
    command: str | None = Field(default=None, max_length=2_000)
    args: list[str] | None = Field(default=None, max_length=100)
    url: str | None = Field(default=None, max_length=2_000)
    auth_type: str | None = Field(default=None, alias="authType", max_length=32)
    timeout_ms: int | None = Field(default=None, alias="timeoutMs", gt=0, le=300_000)
    reconnect_policy: dict[str, object] | None = Field(default=None, alias="reconnectPolicy")


class McpServerResponse(BaseModel):
    server_id: str
    tenant_id: str
    name: str
    transport: str
    status: str
    command: str | None
    url: str | None
    auth_type: str
    timeout_ms: int
    args: list[str] = Field(default_factory=list)
    reconnect_policy: dict[str, object] = Field(default_factory=dict)
    protocol_version: str | None = None
    last_connection_error: str | None = None
    tool_snapshot_hash: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class UpdateMcpAccessPolicyRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    graph_profile: str = Field(
        default="default", alias="graphProfile", min_length=1, max_length=128
    )
    allow_write: bool = Field(default=False, alias="allowWrite")
    allowed_tools: list[str] = Field(default_factory=list, alias="allowedTools", max_length=200)


class McpAccessPolicyEntryResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    server_id: str = Field(alias="serverId")
    graph_profile: str = Field(alias="graphProfile")
    allow_write: bool = Field(alias="allowWrite")
    allowed_tools: list[str] = Field(alias="allowedTools")


class McpAccessPolicyResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    server_id: str = Field(alias="serverId")
    server_name: str = Field(alias="serverName")
    policies: list[McpAccessPolicyEntryResponse]


class SwaggerSpecSourceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=2_000)
    enabled: bool = True
    syncCron: str | None = Field(default=None, max_length=100)
    jiraProjectKey: str | None = Field(default=None, max_length=50)
    confluenceSpaceKey: str | None = Field(default=None, max_length=64)
    bitbucketRepository: str | None = Field(default=None, max_length=120)
    serviceSlug: str | None = Field(default=None, max_length=200)
    ownerTeam: str | None = Field(default=None, max_length=200)


class SwaggerSpecSourceUpdateRequest(BaseModel):
    url: str | None = Field(default=None, max_length=2_000)
    enabled: bool | None = None
    syncCron: str | None = Field(default=None, max_length=100)
    jiraProjectKey: str | None = Field(default=None, max_length=50)
    confluenceSpaceKey: str | None = Field(default=None, max_length=64)
    bitbucketRepository: str | None = Field(default=None, max_length=120)
    serviceSlug: str | None = Field(default=None, max_length=200)
    ownerTeam: str | None = Field(default=None, max_length=200)


class SwaggerPublishRevisionRequest(BaseModel):
    revisionId: str = Field(min_length=1, max_length=200)


def get_container(request: Request) -> AppContainer:
    return cast(AppContainer, request.app.state.reactor)


def require_mcp_store(request: Request):
    mcp_store = get_container(request).mcp_registry_store()
    if mcp_store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MCP registry persistence is not configured",
        )
    return mcp_store


def optional_admin_audit_store(request: Request):
    container = get_container(request)
    accessor = getattr(container, "admin_audit_store", None)
    return accessor() if accessor is not None else None


def optional_runtime_settings_store(request: Request):
    container = get_container(request)
    accessor = getattr(container, "runtime_settings_store", None)
    return accessor() if accessor is not None else None


def require_runtime_settings_store(request: Request):
    store = optional_runtime_settings_store(request)
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="runtime settings persistence is not configured",
        )
    return store


@legacy_router.post(
    "/api/mcp/servers",
    response_model=McpServerResponse,
    status_code=status.HTTP_201_CREATED,
)
@router.post("/servers", response_model=McpServerResponse, status_code=status.HTTP_201_CREATED)
async def register_mcp_server(
    request: Request,
    body: RegisterMcpServerRequest,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> McpServerResponse:
    mcp_store = require_mcp_store(request)
    registration = McpServerRegistration(
        tenant_id=principal.tenant_id,
        name=body.name,
        transport=body.transport,
        command=body.command,
        args=body.args,
        url=body.url,
        auth_type=body.auth_type,
        timeout_ms=body.timeout_ms,
        reconnect_policy=body.reconnect_policy,
    )
    server_id = await mcp_store.register_server(registration)
    record = await mcp_store.find_server_by_name(tenant_id=principal.tenant_id, name=body.name)
    if record is None:
        return McpServerResponse(
            server_id=server_id,
            tenant_id=principal.tenant_id,
            name=body.name,
            transport=body.transport,
            status="registered",
            command=body.command,
            url=body.url,
            auth_type=body.auth_type,
            timeout_ms=body.timeout_ms,
        )
    return mcp_server_response(record)


@legacy_router.get("/api/mcp/servers", response_model=list[McpServerResponse])
@router.get("/servers", response_model=list[McpServerResponse])
async def list_mcp_servers(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> list[McpServerResponse]:
    mcp_store = require_mcp_store(request)
    records = await mcp_store.list_servers(principal.tenant_id)
    return [mcp_server_response(record) for record in records]


@legacy_router.get("/api/mcp/servers/{name}", response_model=McpServerResponse)
@router.get("/servers/{name}", response_model=McpServerResponse)
async def get_mcp_server(
    request: Request,
    name: str,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> McpServerResponse:
    record = await require_mcp_store(request).find_server_by_name(
        tenant_id=principal.tenant_id,
        name=name,
    )
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MCP server not found")
    return mcp_server_response(record)


@legacy_router.put("/api/mcp/servers/{name}", response_model=McpServerResponse)
@router.put("/servers/{name}", response_model=McpServerResponse)
async def update_mcp_server(
    request: Request,
    name: str,
    body: UpdateMcpServerRequest,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> McpServerResponse:
    store = require_mcp_store(request)
    existing = await store.find_server_by_name(tenant_id=principal.tenant_id, name=name)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MCP server not found")
    registration = McpServerRegistration(
        tenant_id=principal.tenant_id,
        name=name,
        transport=body.transport or existing.transport,
        command=body.command if body.command is not None else existing.command,
        args=body.args if body.args is not None else getattr(existing, "args", []),
        url=body.url if body.url is not None else existing.url,
        auth_type=body.auth_type or existing.auth_type,
        timeout_ms=body.timeout_ms or existing.timeout_ms,
        reconnect_policy=(
            body.reconnect_policy
            if body.reconnect_policy is not None
            else getattr(existing, "reconnect_policy", {})
        ),
    )
    try:
        updated = await store.update_server(
            tenant_id=principal.tenant_id,
            name=name,
            registration=registration,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MCP server not found")
    return mcp_server_response(updated)


@legacy_router.delete("/api/mcp/servers/{name}", status_code=status.HTTP_204_NO_CONTENT)
@router.delete("/servers/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mcp_server(
    request: Request,
    name: str,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> Response:
    deleted = await require_mcp_store(request).delete_server(
        tenant_id=principal.tenant_id,
        name=name,
    )
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MCP server not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@legacy_router.post("/api/mcp/servers/{name}/connect", response_model=McpServerResponse)
@router.post("/servers/{name}/connect", response_model=McpServerResponse)
async def connect_mcp_server(
    request: Request,
    name: str,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> McpServerResponse:
    updated = await require_mcp_store(request).set_server_status(
        tenant_id=principal.tenant_id,
        name=name,
        status="healthy",
    )
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MCP server not found")
    return mcp_server_response(updated)


@legacy_router.post("/api/mcp/servers/{name}/disconnect", response_model=McpServerResponse)
@router.post("/servers/{name}/disconnect", response_model=McpServerResponse)
async def disconnect_mcp_server(
    request: Request,
    name: str,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> McpServerResponse:
    updated = await require_mcp_store(request).set_server_status(
        tenant_id=principal.tenant_id,
        name=name,
        status="disabled",
    )
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MCP server not found")
    return mcp_server_response(updated)


def mcp_server_response(record: Any) -> McpServerResponse:
    return McpServerResponse(
        server_id=record.id,
        tenant_id=record.tenant_id,
        name=record.name,
        transport=record.transport,
        status=record.status,
        command=record.command,
        url=record.url,
        auth_type=record.auth_type,
        timeout_ms=record.timeout_ms,
        args=list(getattr(record, "args", [])),
        reconnect_policy=dict(getattr(record, "reconnect_policy", {})),
        protocol_version=getattr(record, "protocol_version", None),
        last_connection_error=getattr(record, "last_connection_error", None),
        tool_snapshot_hash=getattr(record, "tool_snapshot_hash", None),
        created_at=getattr(record, "created_at", None),
        updated_at=getattr(record, "updated_at", None),
    )


@legacy_router.get(
    "/api/mcp/servers/{name}/access-policy",
    response_model=McpAccessPolicyResponse,
    response_model_by_alias=True,
)
@router.get(
    "/servers/{name}/access-policy",
    response_model=McpAccessPolicyResponse,
    response_model_by_alias=True,
)
async def get_mcp_access_policy(
    request: Request,
    name: str,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> McpAccessPolicyResponse:
    store = require_mcp_store(request)
    server = await store.find_server_by_name(tenant_id=principal.tenant_id, name=name)
    if server is None:
        await record_mcp_access_policy_audit(
            request=request,
            principal=principal,
            server_name=name,
            action=AdminAuditAction.READ,
            detail="status=404",
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MCP server not found")
    policies = await store.list_access_policies(
        tenant_id=principal.tenant_id,
        server_id=server.id,
    )
    await record_mcp_access_policy_audit(
        request=request,
        principal=principal,
        server_name=name,
        action=AdminAuditAction.READ,
        detail=f"status=200, policies={len(policies)}",
    )
    return mcp_access_policy_response(server=server, policies=policies)


@legacy_router.put(
    "/api/mcp/servers/{name}/access-policy",
    response_model=McpAccessPolicyResponse,
    response_model_by_alias=True,
)
@router.put(
    "/servers/{name}/access-policy",
    response_model=McpAccessPolicyResponse,
    response_model_by_alias=True,
)
async def update_mcp_access_policy(
    request: Request,
    name: str,
    body: UpdateMcpAccessPolicyRequest,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> McpAccessPolicyResponse:
    store = require_mcp_store(request)
    server = await store.find_server_by_name(tenant_id=principal.tenant_id, name=name)
    if server is None:
        await record_mcp_access_policy_audit(
            request=request,
            principal=principal,
            server_name=name,
            action=AdminAuditAction.UPDATE,
            detail="status=404",
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MCP server not found")
    validation_error = validate_mcp_access_policy_request(body)
    if validation_error is not None:
        await record_mcp_access_policy_audit(
            request=request,
            principal=principal,
            server_name=name,
            action=AdminAuditAction.UPDATE,
            detail=f"status=400, validationError={validation_error}",
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=validation_error)
    record = McpAccessPolicyRecord(
        id=new_id("mcp_policy"),
        tenant_id=principal.tenant_id,
        server_id=server.id,
        graph_profile=body.graph_profile,
        allow_write=body.allow_write,
        allowed_tools=body.allowed_tools,
        created_at=datetime.now(UTC),
    )
    await store.save_access_policy(record)
    policies = await store.list_access_policies(
        tenant_id=principal.tenant_id,
        server_id=server.id,
    )
    await record_mcp_access_policy_audit(
        request=request,
        principal=principal,
        server_name=name,
        action=AdminAuditAction.UPDATE,
        detail=(
            "status=200, "
            f"graphProfile={body.graph_profile}, "
            f"allowWrite={body.allow_write}, "
            f"allowedTools={len(body.allowed_tools)}"
        ),
    )
    return mcp_access_policy_response(server=server, policies=policies)


@legacy_router.delete(
    "/api/mcp/servers/{name}/access-policy",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
@router.delete(
    "/servers/{name}/access-policy",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_mcp_access_policy(
    request: Request,
    name: str,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> Response:
    store = require_mcp_store(request)
    server = await store.find_server_by_name(tenant_id=principal.tenant_id, name=name)
    if server is None:
        await record_mcp_access_policy_audit(
            request=request,
            principal=principal,
            server_name=name,
            action=AdminAuditAction.DELETE,
            detail="status=404",
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MCP server not found")
    deleted = await store.delete_access_policies(tenant_id=principal.tenant_id, server_id=server.id)
    await record_mcp_access_policy_audit(
        request=request,
        principal=principal,
        server_name=name,
        action=AdminAuditAction.DELETE,
        detail=f"status=204, deletedPolicies={deleted}, reset_to_env_defaults=true",
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@legacy_router.post(
    "/api/mcp/servers/{name}/access-policy/emergency-deny-all",
    response_model=McpAccessPolicyResponse,
    response_model_by_alias=True,
)
@router.post(
    "/servers/{name}/access-policy/emergency-deny-all",
    response_model=McpAccessPolicyResponse,
    response_model_by_alias=True,
)
async def emergency_deny_all_mcp_access_policy(
    request: Request,
    name: str,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> McpAccessPolicyResponse:
    store = require_mcp_store(request)
    server = await store.find_server_by_name(tenant_id=principal.tenant_id, name=name)
    if server is None:
        await record_mcp_access_policy_audit(
            request=request,
            principal=principal,
            server_name=name,
            action=AdminAuditAction.UPDATE,
            detail="status=404, emergency_deny_all=true",
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MCP server not found")
    record = McpAccessPolicyRecord(
        id=new_id("mcp_policy"),
        tenant_id=principal.tenant_id,
        server_id=server.id,
        graph_profile="default",
        allow_write=False,
        allowed_tools=[],
        created_at=datetime.now(UTC),
    )
    await store.save_access_policy(record)
    policies = await store.list_access_policies(
        tenant_id=principal.tenant_id,
        server_id=server.id,
    )
    await record_mcp_access_policy_audit(
        request=request,
        principal=principal,
        server_name=name,
        action=AdminAuditAction.UPDATE,
        detail="status=200, emergency_deny_all=true",
    )
    return mcp_access_policy_response(server=server, policies=policies)


def mcp_access_policy_response(*, server: Any, policies: Sequence[Any]) -> McpAccessPolicyResponse:
    return McpAccessPolicyResponse(
        serverId=server.id,
        serverName=server.name,
        policies=[
            McpAccessPolicyEntryResponse(
                id=policy.id,
                serverId=policy.server_id,
                graphProfile=policy.graph_profile,
                allowWrite=policy.allow_write,
                allowedTools=list(policy.allowed_tools),
            )
            for policy in sorted(policies, key=lambda item: item.graph_profile)
        ],
    )


def validate_mcp_access_policy_request(body: UpdateMcpAccessPolicyRequest) -> str | None:
    for index, tool_name in enumerate(body.allowed_tools):
        normalized = tool_name.strip()
        if not normalized:
            return f"allowedTools[{index}] must not be blank"
        if normalized != tool_name:
            return f"allowedTools[{index}] must not contain leading or trailing whitespace"
        if len(tool_name) > 257:
            return f"allowedTools[{index}] must not exceed 257 characters"
        if ":" not in tool_name:
            return f"allowedTools[{index}] must be fully qualified"
    return None


@legacy_router.get(
    "/api/mcp/security",
    response_model=McpSecurityPolicyStateResponse,
    response_model_by_alias=True,
)
@router.get(
    "/security",
    response_model=McpSecurityPolicyStateResponse,
    response_model_by_alias=True,
)
async def get_mcp_security_policy(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> McpSecurityPolicyStateResponse:
    del principal
    effective, stored, config_default = await load_mcp_security_policy_state(
        settings=get_container(request).settings,
        store=optional_runtime_settings_store(request),
    )
    return McpSecurityPolicyStateResponse(
        effective=mcp_security_policy_response(effective),
        stored=mcp_security_policy_response(stored) if stored is not None else None,
        configDefault=mcp_security_policy_response(config_default),
    )


@legacy_router.put(
    "/api/mcp/security",
    response_model=McpSecurityPolicyResponse,
    response_model_by_alias=True,
)
@router.put(
    "/security",
    response_model=McpSecurityPolicyResponse,
    response_model_by_alias=True,
)
async def update_mcp_security_policy(
    request: Request,
    body: UpdateMcpSecurityPolicyRequest,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> McpSecurityPolicyResponse:
    saved = await save_mcp_security_policy(
        store=require_runtime_settings_store(request),
        allowed_server_names=body.allowedServerNames,
        max_tool_output_length=body.maxToolOutputLength,
        actor=current_actor(principal),
    )
    await record_mcp_security_audit(
        request=request,
        principal=principal,
        action=AdminAuditAction.UPDATE,
        detail=(
            f"allowedServers={len(saved.allowed_server_names)}, "
            f"maxToolOutputLength={saved.max_tool_output_length}"
        ),
    )
    return mcp_security_policy_response(saved)


@legacy_router.delete(
    "/api/mcp/security",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
@router.delete(
    "/security",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_mcp_security_policy_endpoint(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> Response:
    await delete_mcp_security_policy(require_runtime_settings_store(request))
    await record_mcp_security_audit(
        request=request,
        principal=principal,
        action=AdminAuditAction.DELETE,
        detail="reset_to_config_defaults=true",
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@legacy_router.get("/api/mcp/servers/{name}/swagger/sources", response_model=None)
@router.get("/servers/{name}/swagger/sources", response_model=None)
async def list_swagger_sources(
    request: Request,
    name: str,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> Response | JSONResponse:
    server = await require_mcp_store(request).find_server_by_name(
        tenant_id=principal.tenant_id,
        name=name,
    )
    if server is None:
        return proxy_error(status.HTTP_404_NOT_FOUND, f"MCP server '{name}' not found")
    config = preflight_config_from_server(server)
    if not isinstance(config, str) and config.token is None:
        response = JSONResponse(content=[])
        response.headers["X-Mcp-Admin-Available"] = "false"
        response.headers["X-Mcp-Admin-Reason"] = "no-admin-token"
        return response
    return await proxy_mcp_admin(
        request=request,
        principal=principal,
        server=server,
        method="GET",
        path="/admin/spec-sources",
        action=AdminAuditAction.LIST_SOURCES,
    )


@legacy_router.get("/api/mcp/servers/{name}/swagger/sources/{source_name}", response_model=None)
@router.get("/servers/{name}/swagger/sources/{source_name}", response_model=None)
async def get_swagger_source(
    request: Request,
    name: str,
    source_name: str,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> Response | JSONResponse:
    return await proxy_mcp_admin_by_name(
        request=request,
        principal=principal,
        server_name=name,
        method="GET",
        path=f"/admin/spec-sources/{source_name}",
        action=AdminAuditAction.GET_SOURCE,
        audit_detail=source_name,
    )


@legacy_router.post("/api/mcp/servers/{name}/swagger/sources", response_model=None)
@router.post("/servers/{name}/swagger/sources", response_model=None)
async def create_swagger_source(
    request: Request,
    name: str,
    body: SwaggerSpecSourceRequest,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> Response | JSONResponse:
    return await proxy_mcp_admin_by_name(
        request=request,
        principal=principal,
        server_name=name,
        method="POST",
        path="/admin/spec-sources",
        body=body.model_dump(exclude_none=True),
        action=AdminAuditAction.CREATE_SOURCE,
        audit_detail=body.name,
    )


@legacy_router.put("/api/mcp/servers/{name}/swagger/sources/{source_name}", response_model=None)
@router.put("/servers/{name}/swagger/sources/{source_name}", response_model=None)
async def update_swagger_source(
    request: Request,
    name: str,
    source_name: str,
    body: SwaggerSpecSourceUpdateRequest,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> Response | JSONResponse:
    return await proxy_mcp_admin_by_name(
        request=request,
        principal=principal,
        server_name=name,
        method="PUT",
        path=f"/admin/spec-sources/{source_name}",
        body=body.model_dump(exclude_none=True),
        action=AdminAuditAction.UPDATE_SOURCE,
        audit_detail=source_name,
    )


@legacy_router.post(
    "/api/mcp/servers/{name}/swagger/sources/{source_name}/sync",
    response_model=None,
)
@router.post("/servers/{name}/swagger/sources/{source_name}/sync", response_model=None)
async def sync_swagger_source(
    request: Request,
    name: str,
    source_name: str,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> Response | JSONResponse:
    return await proxy_mcp_admin_by_name(
        request=request,
        principal=principal,
        server_name=name,
        method="POST",
        path=f"/admin/spec-sources/{source_name}/sync",
        body={},
        action=AdminAuditAction.SYNC_SOURCE,
        audit_detail=source_name,
    )


@legacy_router.get(
    "/api/mcp/servers/{name}/swagger/sources/{source_name}/revisions",
    response_model=None,
)
@router.get("/servers/{name}/swagger/sources/{source_name}/revisions", response_model=None)
async def list_swagger_revisions(
    request: Request,
    name: str,
    source_name: str,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
    limit: int | None = Query(default=None, ge=1, le=500),
) -> Response | JSONResponse:
    query = {"limit": str(limit)} if limit is not None else {}
    return await proxy_mcp_admin_by_name(
        request=request,
        principal=principal,
        server_name=name,
        method="GET",
        path=f"/admin/spec-sources/{source_name}/revisions",
        query=query,
        action=AdminAuditAction.LIST_REVISIONS,
        audit_detail=f"{source_name}?limit={limit}" if limit is not None else source_name,
    )


@legacy_router.get(
    "/api/mcp/servers/{name}/swagger/sources/{source_name}/diff",
    response_model=None,
)
@router.get("/servers/{name}/swagger/sources/{source_name}/diff", response_model=None)
async def get_swagger_diff(
    request: Request,
    name: str,
    source_name: str,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
    from_revision: str | None = Query(default=None, alias="from"),
    to_revision: str | None = Query(default=None, alias="to"),
) -> Response | JSONResponse:
    query = {
        key: value
        for key, value in {"from": from_revision, "to": to_revision}.items()
        if value is not None and value.strip()
    }
    return await proxy_mcp_admin_by_name(
        request=request,
        principal=principal,
        server_name=name,
        method="GET",
        path=f"/admin/spec-sources/{source_name}/diff",
        query=query,
        action=AdminAuditAction.GET_DIFF,
        audit_detail=f"{source_name}:{from_revision or 'auto'}->{to_revision or 'auto'}",
    )


@legacy_router.post(
    "/api/mcp/servers/{name}/swagger/sources/{source_name}/publish",
    response_model=None,
)
@router.post("/servers/{name}/swagger/sources/{source_name}/publish", response_model=None)
async def publish_swagger_revision(
    request: Request,
    name: str,
    source_name: str,
    body: SwaggerPublishRevisionRequest,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> Response | JSONResponse:
    return await proxy_mcp_admin_by_name(
        request=request,
        principal=principal,
        server_name=name,
        method="POST",
        path=f"/admin/spec-sources/{source_name}/publish",
        body=body.model_dump(),
        action=AdminAuditAction.PUBLISH_REVISION,
        audit_detail=f"{source_name}:{body.revisionId}",
    )


@legacy_router.get("/api/mcp/servers/{name}/preflight", response_model=None)
@router.get("/servers/{name}/preflight", response_model=None)
async def get_mcp_preflight(
    request: Request,
    name: str,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> Response | JSONResponse:
    store = require_mcp_store(request)
    server = await store.find_server_by_name(tenant_id=principal.tenant_id, name=name)
    if server is None:
        return proxy_error(status.HTTP_404_NOT_FOUND, f"MCP server '{name}' not found")

    config = preflight_config_from_server(server)
    if isinstance(config, str):
        response: Response | JSONResponse = proxy_error(status.HTTP_400_BAD_REQUEST, config)
        await record_preflight_audit(request, principal, name, response, None)
        return response
    if config.hmac_required and config.hmac_secret is None:
        response = proxy_error(
            status.HTTP_400_BAD_REQUEST,
            f"MCP server '{name}' requires HMAC but admin HMAC secret is missing",
        )
        await record_preflight_audit(request, principal, name, response, None)
        return response
    if config.token is None:
        response = Response(status_code=status.HTTP_204_NO_CONTENT)
        response.headers["X-Preflight-Skipped"] = "no-admin-token"
        await record_preflight_audit(request, principal, name, response, None)
        return response

    headers = {
        "X-Admin-Token": config.token,
        "X-Admin-Actor": current_actor(principal),
        "X-Request-Id": request.headers.get("X-Request-Id", ""),
    }
    if config.hmac_secret is not None:
        timestamp = request.headers.get("X-Admin-Timestamp") or str(int(time()))
        headers["X-Admin-Timestamp"] = timestamp
        headers["X-Admin-Signature"] = preflight_hmac_signature(
            secret=config.hmac_secret,
            method="GET",
            path=ADMIN_PREFLIGHT_PATH,
            query="",
            body="",
            timestamp=timestamp,
        )
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(
                config.timeout_ms / 1000,
                connect=config.connect_timeout_ms / 1000,
            )
        ) as client:
            upstream = await client.get(admin_preflight_url(config.base_url), headers=headers)
    except httpx.TimeoutException:
        response = proxy_error(
            status.HTTP_504_GATEWAY_TIMEOUT,
            f"MCP admin API timed out after {config.timeout_ms}ms",
        )
        await record_preflight_audit(request, principal, name, response, None)
        return response
    except httpx.HTTPError:
        response = proxy_error(status.HTTP_502_BAD_GATEWAY, "Failed to call MCP admin API")
        await record_preflight_audit(request, principal, name, response, None)
        return response

    response = upstream_response(upstream)
    await record_preflight_audit(request, principal, name, response, response_body(upstream))
    return response


def proxy_error(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": message})


def mcp_security_policy_response(policy: McpSecurityPolicy) -> McpSecurityPolicyResponse:
    return McpSecurityPolicyResponse(
        allowedServerNames=sorted(policy.allowed_server_names),
        maxToolOutputLength=policy.max_tool_output_length,
        createdAt=epoch_millis(policy.created_at),
        updatedAt=epoch_millis(policy.updated_at),
    )


async def record_mcp_security_audit(
    *,
    request: Request,
    principal: AuthPrincipal,
    action: AdminAuditAction,
    detail: str,
) -> None:
    store = optional_admin_audit_store(request)
    if store is None:
        return
    await store.save(
        AdminAuditLog(
            category="mcp_security",
            action=action,
            actor=current_actor(principal),
            resource_type="mcp_security",
            resource_id="singleton",
            detail=detail,
        ),
        tenant_id=principal.tenant_id,
    )


async def record_mcp_access_policy_audit(
    *,
    request: Request,
    principal: AuthPrincipal,
    server_name: str,
    action: AdminAuditAction,
    detail: str,
) -> None:
    store = optional_admin_audit_store(request)
    if store is None:
        return
    await store.save(
        AdminAuditLog(
            category="mcp_access_policy",
            action=action,
            actor=current_actor(principal),
            resource_type="mcp_server",
            resource_id=server_name,
            detail=detail,
        ),
        tenant_id=principal.tenant_id,
    )


def upstream_response(upstream: httpx.Response) -> Response | JSONResponse:
    content_type = upstream.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            return JSONResponse(status_code=upstream.status_code, content=upstream.json())
        except ValueError:
            pass
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=content_type or None,
    )


async def proxy_mcp_admin_by_name(
    *,
    request: Request,
    principal: AuthPrincipal,
    server_name: str,
    method: str,
    path: str,
    action: AdminAuditAction,
    query: Mapping[str, str] | None = None,
    body: Mapping[str, Any] | None = None,
    audit_detail: str | None = None,
) -> Response | JSONResponse:
    server = await require_mcp_store(request).find_server_by_name(
        tenant_id=principal.tenant_id,
        name=server_name,
    )
    if server is None:
        return proxy_error(status.HTTP_404_NOT_FOUND, f"MCP server '{server_name}' not found")
    return await proxy_mcp_admin(
        request=request,
        principal=principal,
        server=server,
        method=method,
        path=path,
        action=action,
        query=query,
        body=body,
        audit_detail=audit_detail,
    )


async def proxy_mcp_admin(
    *,
    request: Request,
    principal: AuthPrincipal,
    server: Any,
    method: str,
    path: str,
    action: AdminAuditAction,
    query: Mapping[str, str] | None = None,
    body: Mapping[str, Any] | None = None,
    audit_detail: str | None = None,
) -> Response | JSONResponse:
    server_name = str(getattr(server, "name", "unknown"))
    config = preflight_config_from_server(server)
    if isinstance(config, str):
        response: Response | JSONResponse = proxy_error(status.HTTP_400_BAD_REQUEST, config)
        await record_swagger_audit(request, principal, server_name, action, response, audit_detail)
        return response
    if config.token is None:
        response = proxy_error(
            status.HTTP_400_BAD_REQUEST,
            f"MCP server '{server_name}' has no admin token. Set scoped admin token",
        )
        await record_swagger_audit(request, principal, server_name, action, response, audit_detail)
        return response
    if config.hmac_required and config.hmac_secret is None:
        response = proxy_error(
            status.HTTP_400_BAD_REQUEST,
            f"MCP server '{server_name}' requires HMAC but admin HMAC secret is missing",
        )
        await record_swagger_audit(request, principal, server_name, action, response, audit_detail)
        return response

    raw_query = urlencode(dict(query or {}), safe="/")
    target_path = encode_admin_path(path)
    payload = body or {}
    payload_json = "" if method == "GET" else json_dumps(payload)
    headers = {
        "X-Admin-Token": config.token,
        "X-Admin-Actor": current_actor(principal),
        "X-Request-Id": request.headers.get("X-Request-Id", ""),
    }
    if config.hmac_secret is not None:
        timestamp = request.headers.get("X-Admin-Timestamp") or str(int(time()))
        headers["X-Admin-Timestamp"] = timestamp
        headers["X-Admin-Signature"] = preflight_hmac_signature(
            secret=config.hmac_secret,
            method=method,
            path=target_path,
            query=raw_query,
            body=payload_json,
            timestamp=timestamp,
        )
    url = f"{config.base_url}{target_path}"
    if raw_query:
        url = f"{url}?{raw_query}"
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(
                config.timeout_ms / 1000,
                connect=config.connect_timeout_ms / 1000,
            )
        ) as client:
            upstream = await client.request(
                method,
                url,
                headers=headers,
                content=payload_json if method != "GET" else None,
            )
    except httpx.TimeoutException:
        response = proxy_error(
            status.HTTP_504_GATEWAY_TIMEOUT,
            f"MCP admin API timed out after {config.timeout_ms}ms",
        )
        await record_swagger_audit(request, principal, server_name, action, response, audit_detail)
        return response
    except httpx.HTTPError:
        response = proxy_error(status.HTTP_502_BAD_GATEWAY, "Failed to call MCP admin API")
        await record_swagger_audit(request, principal, server_name, action, response, audit_detail)
        return response

    response = upstream_response(upstream)
    await record_swagger_audit(request, principal, server_name, action, response, audit_detail)
    return response


def json_dumps(payload: Mapping[str, Any]) -> str:
    import json

    return json.dumps(dict(payload), separators=(",", ":"))


def encode_admin_path(path: str) -> str:
    parts = [quote(part, safe="") for part in path.split("/") if part]
    return "/" + "/".join(parts)


async def record_swagger_audit(
    request: Request,
    principal: AuthPrincipal,
    server_name: str,
    action: AdminAuditAction,
    response: Response | JSONResponse,
    detail: str | None,
) -> None:
    store = optional_admin_audit_store(request)
    if store is None:
        return
    suffix = f", detail={detail}" if detail else ""
    await store.save(
        AdminAuditLog(
            category="mcp_swagger_catalog",
            action=action,
            actor=current_actor(principal),
            resource_type="mcp_server",
            resource_id=server_name,
            detail=f"status={response.status_code}{suffix}",
        ),
        tenant_id=principal.tenant_id,
    )


def response_body(upstream: httpx.Response) -> Any:
    try:
        return upstream.json()
    except ValueError:
        return None


async def record_preflight_audit(
    request: Request,
    principal: AuthPrincipal,
    server_name: str,
    response: Response | JSONResponse,
    body: Any,
) -> None:
    store = optional_admin_audit_store(request)
    if store is None:
        return
    await store.save(
        AdminAuditLog(
            category="mcp_preflight",
            action=AdminAuditAction.READ,
            actor=current_actor(principal),
            resource_type="mcp_server",
            resource_id=server_name,
            detail=preflight_audit_detail(response.status_code, body),
        ),
        tenant_id=principal.tenant_id,
    )


def preflight_audit_detail(status_code: int, body: Any) -> str:
    parts = [f"status={status_code}"]
    if isinstance(body, Mapping):
        mapped_body = cast(Mapping[str, Any], body)
        append_detail(parts, "policySource", mapped_body.get("policySource"))
        append_bool_detail(parts, "ok", mapped_body.get("ok"))
        append_bool_detail(
            parts,
            "readyForProduction",
            mapped_body.get("readyForProduction"),
        )
        summary = mapped_body.get("summary")
        if isinstance(summary, Mapping):
            mapped_summary = cast(Mapping[str, Any], summary)
            append_detail(parts, "passCount", mapped_summary.get("passCount"))
            append_detail(parts, "warnCount", mapped_summary.get("warnCount"))
            append_detail(parts, "failCount", mapped_summary.get("failCount"))
    return ", ".join(parts)


def append_detail(parts: list[str], key: str, value: object) -> None:
    if value is None:
        return
    normalized = str(value).strip()
    if normalized:
        parts.append(f"{key}={normalized}")


def append_bool_detail(parts: list[str], key: str, value: object) -> None:
    if isinstance(value, bool):
        parts.append(f"{key}={str(value).lower()}")
