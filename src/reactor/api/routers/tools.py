from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Protocol, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from reactor.admin.audit import AdminAuditAction, AdminAuditLog
from reactor.api.auth import require_any_admin
from reactor.api.schemas.tools import (
    ToolCatalogListResponse,
    ToolCatalogResponse,
    ToolCatalogUpsertRequest,
    ToolEnabledUpdateRequest,
    ToolPolicyResponse,
    ToolPolicyStateResponse,
    UpdateToolPolicyRequest,
)
from reactor.auth.rbac import AuthPrincipal, current_actor
from reactor.core.container import AppContainer
from reactor.kernel.ids import new_id
from reactor.persistence.tool_invocation_store import ToolInvocationRecord
from reactor.persistence.tool_store import ToolCatalogRecord
from reactor.tools.catalog import ToolSpec
from reactor.tools.policy import (
    DynamicToolPolicy,
    ToolPolicySettingsStore,
    ToolPolicyState,
    delete_tool_policy,
    load_tool_policy_state,
    save_tool_policy,
)

router = APIRouter(tags=["tools"])


class ToolCatalogStore(Protocol):
    async def save(self, record: ToolCatalogRecord) -> ToolCatalogRecord: ...

    async def list_catalog(self, *, tenant_id: str) -> list[ToolCatalogRecord]: ...

    async def find_catalog(
        self,
        *,
        tenant_id: str,
        namespace: str,
        name: str,
    ) -> ToolCatalogRecord | None: ...


class ToolInvocationStore(Protocol):
    async def list_between(
        self,
        *,
        tenant_id: str,
        from_time: datetime,
        to_time: datetime,
        limit: int = 500,
    ) -> list[ToolInvocationRecord]: ...


class AdminAuditStore(Protocol):
    async def save(
        self,
        record: AdminAuditLog,
        *,
        tenant_id: str,
    ) -> AdminAuditLog: ...


@dataclass(frozen=True)
class ToolOutcomeSnapshot:
    tool: str
    server: str
    outcome: str
    count: float


def get_container(request: Request) -> AppContainer:
    return cast(AppContainer, request.app.state.reactor)


def require_tool_catalog_store(request: Request) -> ToolCatalogStore:
    store = get_container(request).tool_store()
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="tool catalog persistence is not configured",
        )
    return cast(ToolCatalogStore, store)


def require_tool_invocation_store(request: Request) -> ToolInvocationStore:
    container = get_container(request)
    accessor = getattr(container, "tool_invocation_store", None)
    store = accessor() if accessor is not None else None
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="tool invocation persistence is not configured",
        )
    return cast(ToolInvocationStore, store)


def optional_runtime_settings_store(request: Request) -> ToolPolicySettingsStore | None:
    accessor = getattr(get_container(request), "runtime_settings_store", None)
    store = accessor() if accessor is not None else None
    return cast(ToolPolicySettingsStore, store) if store is not None else None


def require_runtime_settings_store(request: Request) -> ToolPolicySettingsStore:
    store = optional_runtime_settings_store(request)
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="runtime settings persistence is not configured",
        )
    return store


def optional_admin_audit_store(request: Request) -> AdminAuditStore | None:
    accessor = getattr(get_container(request), "admin_audit_store", None)
    store = accessor() if accessor is not None else None
    return cast(AdminAuditStore, store) if store is not None else None


@router.get(
    "/api/tool-policy",
    response_model=ToolPolicyStateResponse,
    response_model_by_alias=True,
)
@router.get(
    "/v1/tool-policy",
    response_model=ToolPolicyStateResponse,
    response_model_by_alias=True,
)
async def get_tool_policy(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> ToolPolicyStateResponse:
    state = await load_tool_policy_state(
        optional_runtime_settings_store(request),
        tenant_id=principal.tenant_id,
    )
    return tool_policy_state_response(state)


@router.put(
    "/api/tool-policy",
    response_model=ToolPolicyResponse,
    response_model_by_alias=True,
)
@router.put(
    "/v1/tool-policy",
    response_model=ToolPolicyResponse,
    response_model_by_alias=True,
)
async def update_tool_policy(
    request: Request,
    body: UpdateToolPolicyRequest,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> ToolPolicyResponse:
    saved = await save_tool_policy(
        require_runtime_settings_store(request),
        tenant_id=principal.tenant_id,
        enabled=body.enabled,
        write_tool_names=body.write_tool_names,
        deny_write_channels=body.deny_write_channels,
        allow_write_tool_names_in_deny_channels=body.allow_write_tool_names_in_deny_channels,
        allow_write_tool_names_by_channel=body.allow_write_tool_names_by_channel,
        deny_write_message=body.deny_write_message,
        actor=current_actor(principal),
    )
    await record_tool_policy_audit(
        request=request,
        principal=principal,
        action=AdminAuditAction.UPDATE,
        detail=(
            f"enabled={saved.enabled}, "
            f"writeTools={len(saved.write_tool_names)}, "
            f"denyChannels={len(saved.deny_write_channels)}"
        ),
    )
    return tool_policy_response(saved)


@router.delete("/api/tool-policy", status_code=status.HTTP_204_NO_CONTENT)
@router.delete("/v1/tool-policy", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tool_policy_endpoint(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> Response:
    await delete_tool_policy(require_runtime_settings_store(request), tenant_id=principal.tenant_id)
    await record_tool_policy_audit(
        request=request,
        principal=principal,
        action=AdminAuditAction.DELETE,
        detail="reset_to_config_defaults=true",
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/api/admin/tools",
    response_model=ToolCatalogListResponse,
    response_model_by_alias=True,
)
@router.get(
    "/v1/admin/tools",
    response_model=ToolCatalogListResponse,
    response_model_by_alias=True,
)
async def list_tools(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> ToolCatalogListResponse:
    rows = await require_tool_catalog_store(request).list_catalog(tenant_id=principal.tenant_id)
    return ToolCatalogListResponse(
        total=len(rows),
        items=[tool_catalog_response(row) for row in rows],
    )


@router.get("/api/admin/tools/stats")
@router.get("/v1/admin/tools/stats")
async def tool_stats(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
    server: str | None = None,
    days: int = Query(default=30, ge=1, le=365),
) -> dict[str, object]:
    counters = await read_tool_outcome_counters(
        request,
        tenant_id=principal.tenant_id,
        server=server,
        days=days,
    )
    return tool_stats_payload(counters)


@router.get("/api/admin/tools/accuracy")
@router.get("/v1/admin/tools/accuracy")
async def tool_accuracy(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
    days: int = Query(default=30, ge=1, le=365),
) -> dict[str, float]:
    counters = await read_tool_outcome_counters(
        request,
        tenant_id=principal.tenant_id,
        server=None,
        days=days,
    )
    total = sum(counter.count for counter in counters)
    ok_count = count_for(counters, "ok")
    return {
        "total": total,
        "ok": ok_count,
        "accuracy": ok_count / total if total else 0.0,
        "invalidCallRate": invalid_call_rate(counters),
        "timeoutRate": rate_for(counters, "timeout"),
        "notFoundRate": rate_for(counters, "not_found"),
    }


@router.get(
    "/api/admin/tools/{namespace}/{name}",
    response_model=ToolCatalogResponse,
    response_model_by_alias=True,
)
@router.get(
    "/v1/admin/tools/{namespace}/{name}",
    response_model=ToolCatalogResponse,
    response_model_by_alias=True,
)
async def get_tool(
    request: Request,
    namespace: str,
    name: str,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> ToolCatalogResponse:
    record = await require_tool_catalog_store(request).find_catalog(
        tenant_id=principal.tenant_id,
        namespace=namespace,
        name=name,
    )
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tool not found")
    return tool_catalog_response(record)


@router.put(
    "/api/admin/tools/{namespace}/{name}",
    response_model=ToolCatalogResponse,
    response_model_by_alias=True,
)
@router.put(
    "/v1/admin/tools/{namespace}/{name}",
    response_model=ToolCatalogResponse,
    response_model_by_alias=True,
)
async def upsert_tool(
    request: Request,
    namespace: str,
    name: str,
    body: ToolCatalogUpsertRequest,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> ToolCatalogResponse:
    existing = await require_tool_catalog_store(request).find_catalog(
        tenant_id=principal.tenant_id,
        namespace=namespace,
        name=name,
    )
    now = datetime.now(UTC)
    requires_approval = approval_required_for(body, namespace=namespace, name=name)
    record = ToolCatalogRecord(
        id=existing.id if existing is not None else new_id("tool"),
        tenant_id=principal.tenant_id,
        namespace=namespace,
        name=name,
        description=body.description.strip(),
        risk_level=body.risk_level.strip(),
        input_schema=body.input_schema,
        output_schema=body.output_schema,
        enabled=body.enabled,
        requires_approval=requires_approval,
        timeout_ms=body.timeout_ms,
        created_at=existing.created_at if existing is not None else now,
        updated_at=now,
    )
    try:
        saved = await require_tool_catalog_store(request).save(record)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return tool_catalog_response(saved)


@router.patch(
    "/api/admin/tools/{namespace}/{name}/enabled",
    response_model=ToolCatalogResponse,
    response_model_by_alias=True,
)
@router.patch(
    "/v1/admin/tools/{namespace}/{name}/enabled",
    response_model=ToolCatalogResponse,
    response_model_by_alias=True,
)
async def update_tool_enabled(
    request: Request,
    namespace: str,
    name: str,
    body: ToolEnabledUpdateRequest,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> ToolCatalogResponse:
    store = require_tool_catalog_store(request)
    existing = await store.find_catalog(
        tenant_id=principal.tenant_id,
        namespace=namespace,
        name=name,
    )
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tool not found")
    saved = await store.save(
        ToolCatalogRecord(
            id=existing.id,
            tenant_id=existing.tenant_id,
            namespace=existing.namespace,
            name=existing.name,
            description=existing.description,
            risk_level=existing.risk_level,
            input_schema=existing.input_schema,
            output_schema=existing.output_schema,
            enabled=body.enabled,
            requires_approval=existing.requires_approval,
            timeout_ms=existing.timeout_ms,
            created_at=existing.created_at,
            updated_at=datetime.now(UTC),
        )
    )
    return tool_catalog_response(saved)


def approval_required_for(
    body: ToolCatalogUpsertRequest,
    *,
    namespace: str,
    name: str,
) -> bool:
    spec = ToolSpec(
        tenant_id="tenant",
        namespace=namespace,
        name=name,
        description=body.description,
        risk_level=body.risk_level,
        input_schema=body.input_schema,
        output_schema=body.output_schema,
        enabled=body.enabled,
        requires_approval=body.requires_approval,
        timeout_ms=body.timeout_ms,
    )
    try:
        spec.validate()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return spec.approval_required


def tool_catalog_response(record: ToolCatalogRecord) -> ToolCatalogResponse:
    return ToolCatalogResponse(
        id=record.id,
        tenantId=record.tenant_id,
        namespace=record.namespace,
        name=record.name,
        qualifiedName=f"{record.namespace}:{record.name}",
        description=record.description,
        riskLevel=record.risk_level,
        inputSchema=record.input_schema,
        outputSchema=record.output_schema,
        enabled=record.enabled,
        requiresApproval=record.requires_approval,
        timeoutMs=record.timeout_ms,
        createdAt=record.created_at,
        updatedAt=record.updated_at,
    )


def tool_policy_state_response(state: ToolPolicyState) -> ToolPolicyStateResponse:
    return ToolPolicyStateResponse(
        configEnabled=state.config_enabled,
        dynamicEnabled=state.dynamic_enabled,
        effective=tool_policy_response(state.effective),
        stored=tool_policy_response(state.stored) if state.stored is not None else None,
    )


def tool_policy_response(policy: DynamicToolPolicy) -> ToolPolicyResponse:
    return ToolPolicyResponse(
        enabled=policy.enabled,
        writeToolNames=list(policy.write_tool_names),
        denyWriteChannels=list(policy.deny_write_channels),
        allowWriteToolNamesInDenyChannels=list(policy.allow_write_tool_names_in_deny_channels),
        allowWriteToolNamesByChannel={
            key: list(value) for key, value in policy.allow_write_tool_names_by_channel.items()
        },
        denyWriteMessage=policy.deny_write_message,
        createdAt=policy.created_at,
        updatedAt=policy.updated_at,
    )


async def record_tool_policy_audit(
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
            category="tool_policy",
            action=action,
            actor=current_actor(principal),
            resource_type="tool_policy",
            resource_id="singleton",
            detail=detail,
        ),
        tenant_id=principal.tenant_id,
    )


async def read_tool_outcome_counters(
    request: Request,
    *,
    tenant_id: str,
    server: str | None,
    days: int,
) -> list[ToolOutcomeSnapshot]:
    to_time = datetime.now(UTC)
    from_time = to_time - timedelta(days=days)
    records = await require_tool_invocation_store(request).list_between(
        tenant_id=tenant_id,
        from_time=from_time,
        to_time=to_time,
        limit=5000,
    )
    buckets: dict[tuple[str, str, str], float] = defaultdict(float)
    for record in records:
        parsed_server, tool_name = split_tool_id(record.tool_id)
        if server and parsed_server != server:
            continue
        outcome = tool_outcome(record)
        buckets[(tool_name, parsed_server, outcome)] += 1.0
    return [
        ToolOutcomeSnapshot(tool=tool, server=server_name, outcome=outcome, count=count)
        for (tool, server_name, outcome), count in buckets.items()
    ]


def tool_stats_payload(counters: list[ToolOutcomeSnapshot]) -> dict[str, object]:
    total = sum(counter.count for counter in counters)
    ok_count = count_for(counters, "ok")
    by_outcome: dict[str, float] = defaultdict(float)
    by_server: dict[str, float] = defaultdict(float)
    for counter in counters:
        by_outcome[counter.outcome] += counter.count
        by_server[counter.server] += counter.count
    return {
        "total": total,
        "accuracy": ok_count / total if total else 0.0,
        "byOutcome": dict(sorted(by_outcome.items())),
        "byServer": dict(sorted(by_server.items())),
        "byTool": [
            {
                "tool": counter.tool,
                "server": counter.server,
                "outcome": counter.outcome,
                "count": counter.count,
            }
            for counter in sorted(
                counters,
                key=lambda item: (-item.count, item.tool, item.server, item.outcome),
            )[:50]
        ],
    }


def split_tool_id(tool_id: str) -> tuple[str, str]:
    if ":" in tool_id:
        server, tool = tool_id.split(":", 1)
    elif "/" in tool_id:
        server, tool = tool_id.split("/", 1)
    else:
        server, tool = "local", tool_id
    return server or "unknown", tool or "unknown"


def tool_outcome(record: ToolInvocationRecord) -> str:
    status_value = record.status.strip().lower()
    if status_value in {"ok", "success", "succeeded", "completed", "complete"}:
        return "ok"
    if status_value in {"timeout", "timed_out"}:
        return "timeout"
    if status_value in {"not_found", "not-found", "missing"}:
        return "not_found"
    if status_value in {"failed", "failure", "error", "invalid", "invalid_arg"}:
        return "failed"
    error_class = ""
    if record.error_payload is not None:
        error_class = str(record.error_payload.get("error_class", "")).strip().lower()
    if "timeout" in error_class:
        return "timeout"
    if "not_found" in error_class or "not found" in error_class:
        return "not_found"
    return status_value or "unknown"


def count_for(counters: list[ToolOutcomeSnapshot], outcome: str) -> float:
    return sum(counter.count for counter in counters if counter.outcome == outcome)


def rate_for(counters: list[ToolOutcomeSnapshot], outcome: str) -> float:
    total = sum(counter.count for counter in counters)
    if total == 0:
        return 0.0
    return count_for(counters, outcome) / total


def invalid_call_rate(counters: list[ToolOutcomeSnapshot]) -> float:
    total = sum(counter.count for counter in counters)
    if total == 0:
        return 0.0
    invalid_count = sum(
        counter.count
        for counter in counters
        if counter.outcome not in {"ok", "timeout", "not_found"}
    )
    return invalid_count / total
