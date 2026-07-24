from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from reactor.agents.langchain_middleware import (
    LangChainMiddlewarePolicy,
    build_langchain_agent_middleware,
    default_langchain_middleware_policy,
    langchain_middleware_policy_from_mapping,
)
from reactor.api.auth import require_permission
from reactor.api.schemas.runtime_settings import (
    LangChainMiddlewareChainPreviewResponse,
    LangChainMiddlewarePiiRuleResponse,
    LangChainMiddlewarePolicyDiagnosticsResponse,
    LangChainMiddlewarePolicyPreviewRequest,
    LangChainMiddlewarePolicyPreviewResponse,
    LangChainMiddlewarePolicyResponse,
    RuntimeSettingResponse,
    RuntimeSettingsEffectiveResponse,
    RuntimeSettingUpdateRequest,
    RuntimeSettingUpdateResponse,
    ToolProfileBudgetDiagnosticsResponse,
    ToolProfileBudgetPreviewRequest,
    ToolProfileBudgetPreviewResponse,
    ToolProfileBudgetPreviewToolRequest,
    ToolProfileBudgetResponse,
)
from reactor.auth.rbac import AuthPrincipal
from reactor.core.container import AppContainer
from reactor.core.runtime_settings import runtime_setting_value
from reactor.core.settings import Settings
from reactor.persistence.runtime_settings_store import SqlAlchemyRuntimeSettingsStore
from reactor.runs.service import (
    ToolProfileBudget,
    ToolSpecProvider,
    apply_tool_profile_budget_with_evidence,
    tool_profile_budget_from_mapping,
)
from reactor.runtime_settings.service import (
    GLOBAL_TENANT_ID,
    RuntimeSettingRecord,
    RuntimeSettingUpdate,
)
from reactor.tools.catalog import ToolSpec

router = APIRouter(tags=["runtime-settings"])


def get_container(request: Request) -> AppContainer:
    return cast(AppContainer, request.app.state.reactor)


def require_runtime_settings_store(request: Request) -> SqlAlchemyRuntimeSettingsStore:
    store = get_container(request).runtime_settings_store()
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="runtime settings persistence is not configured",
        )
    return store


def optional_tool_provider(request: Request) -> ToolSpecProvider | None:
    accessor = getattr(get_container(request), "tool_store", None)
    if accessor is None:
        return None
    return cast(ToolSpecProvider | None, accessor())


@router.get(
    "/v1/admin/settings",
    response_model=list[RuntimeSettingResponse],
    response_model_by_alias=True,
)
@router.get(
    "/api/admin/settings",
    response_model=list[RuntimeSettingResponse],
    response_model_by_alias=True,
)
async def list_runtime_settings(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_permission("settings:read"))],
    tenant_id: str | None = Query(default=None, min_length=1, max_length=128),
) -> list[RuntimeSettingResponse]:
    store = require_runtime_settings_store(request)
    records = await store.list(tenant_id=runtime_settings_tenant(principal, tenant_id))
    return [runtime_setting_response(record) for record in records]


@router.get(
    "/v1/admin/settings/effective",
    response_model=RuntimeSettingsEffectiveResponse,
    response_model_by_alias=True,
)
@router.get(
    "/api/admin/settings/effective",
    response_model=RuntimeSettingsEffectiveResponse,
    response_model_by_alias=True,
)
async def get_effective_runtime_settings_diagnostics(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_permission("settings:read"))],
    tenant_id: str = Query(default=GLOBAL_TENANT_ID, min_length=1, max_length=128),
) -> RuntimeSettingsEffectiveResponse:
    require_runtime_settings_store(request)
    resolved_tenant_id = runtime_settings_tenant(principal, tenant_id)
    result = await get_container(request).effective_settings(tenant_id=resolved_tenant_id)
    return RuntimeSettingsEffectiveResponse(
        tenantId=resolved_tenant_id,
        appliedKeys=list(result.applied_keys),
        ignoredKeys=list(result.ignored_keys),
        errors=dict(result.errors),
    )


@router.get(
    "/v1/admin/settings/langchain/middleware-policy",
    response_model=LangChainMiddlewarePolicyDiagnosticsResponse,
    response_model_by_alias=True,
)
@router.get(
    "/api/admin/settings/langchain/middleware-policy",
    response_model=LangChainMiddlewarePolicyDiagnosticsResponse,
    response_model_by_alias=True,
)
async def get_langchain_middleware_policy_diagnostics(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_permission("settings:read"))],
    tenant_id: str | None = Query(default=None, min_length=1, max_length=128),
) -> LangChainMiddlewarePolicyDiagnosticsResponse:
    store = require_runtime_settings_store(request)
    resolved_tenant_id = runtime_settings_tenant(principal, tenant_id)
    records = list(await store.list(tenant_id=resolved_tenant_id))
    if resolved_tenant_id != GLOBAL_TENANT_ID:
        records.extend(await store.list(tenant_id=GLOBAL_TENANT_ID))
    return langchain_middleware_policy_diagnostics(
        records,
        tenant_id=resolved_tenant_id,
        settings=get_container(request).settings,
        default_policy=default_langchain_middleware_policy(get_container(request).settings),
    )


@router.post(
    "/v1/admin/settings/langchain/middleware-policy/preview",
    response_model=LangChainMiddlewarePolicyPreviewResponse,
    response_model_by_alias=True,
)
@router.post(
    "/api/admin/settings/langchain/middleware-policy/preview",
    response_model=LangChainMiddlewarePolicyPreviewResponse,
    response_model_by_alias=True,
)
async def preview_langchain_middleware_policy(
    request: Request,
    body: LangChainMiddlewarePolicyPreviewRequest,
    principal: Annotated[AuthPrincipal, Depends(require_permission("settings:write"))],
    tenant_id: str | None = Query(default=None, min_length=1, max_length=128),
) -> LangChainMiddlewarePolicyPreviewResponse:
    resolved_tenant_id = runtime_settings_tenant(principal, tenant_id)
    policy = langchain_middleware_policy_from_mapping(body.policy)
    if policy is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid langchain.middleware_policy",
        )
    middleware = build_langchain_agent_middleware(
        get_container(request).settings,
        policy=policy,
        interrupt_on_tools=body.interrupt_on_tools,
    )
    return LangChainMiddlewarePolicyPreviewResponse(
        tenantId=resolved_tenant_id,
        key=LANGCHAIN_MIDDLEWARE_POLICY_SETTING_KEY,
        status="preview",
        source="request",
        reason=None,
        policy=langchain_middleware_policy_response(policy),
        middlewareChain=langchain_middleware_chain_preview_response(
            middleware,
            interrupt_on_tools=body.interrupt_on_tools,
        ),
    )


@router.get(
    "/v1/admin/settings/tools/profile-budget",
    response_model=ToolProfileBudgetDiagnosticsResponse,
    response_model_by_alias=True,
)
@router.get(
    "/api/admin/settings/tools/profile-budget",
    response_model=ToolProfileBudgetDiagnosticsResponse,
    response_model_by_alias=True,
)
async def get_tool_profile_budget_diagnostics(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_permission("settings:read"))],
    tenant_id: str | None = Query(default=None, min_length=1, max_length=128),
) -> ToolProfileBudgetDiagnosticsResponse:
    store = require_runtime_settings_store(request)
    resolved_tenant_id = runtime_settings_tenant(principal, tenant_id)
    records = list(await store.list(tenant_id=resolved_tenant_id))
    if resolved_tenant_id != GLOBAL_TENANT_ID:
        records.extend(await store.list(tenant_id=GLOBAL_TENANT_ID))
    tool_provider = optional_tool_provider(request)
    tools = (
        list(await tool_provider.list_enabled_tool_specs(resolved_tenant_id))
        if tool_provider is not None
        else None
    )
    return tool_profile_budget_diagnostics(
        records,
        tenant_id=resolved_tenant_id,
        tools=tools,
    )


@router.post(
    "/v1/admin/settings/tools/profile-budget/preview",
    response_model=ToolProfileBudgetPreviewResponse,
    response_model_by_alias=True,
)
@router.post(
    "/api/admin/settings/tools/profile-budget/preview",
    response_model=ToolProfileBudgetPreviewResponse,
    response_model_by_alias=True,
)
async def preview_tool_profile_budget(
    body: ToolProfileBudgetPreviewRequest,
    principal: Annotated[AuthPrincipal, Depends(require_permission("settings:write"))],
    tenant_id: str | None = Query(default=None, min_length=1, max_length=128),
) -> ToolProfileBudgetPreviewResponse:
    resolved_tenant_id = runtime_settings_tenant(principal, tenant_id)
    budget = tool_profile_budget_from_mapping(body.budget)
    if budget is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid tools.profile_budget",
        )
    tools = [
        preview_tool_spec(tool, tenant_id=resolved_tenant_id) for tool in body.configured_tools
    ]
    for tool in tools:
        try:
            tool.validate()
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"invalid configured tool: {error}",
            ) from error
    application = apply_tool_profile_budget_with_evidence(tools, budget)
    return ToolProfileBudgetPreviewResponse(
        tenantId=resolved_tenant_id,
        key=TOOL_PROFILE_BUDGET_SETTING_KEY,
        status="preview",
        source="request",
        reason=None,
        budget=tool_profile_budget_response(budget),
        configuredToolCount=len(tools),
        activeToolCount=len(application.tools),
        activeTools=[tool.qualified_name for tool in application.tools],
        droppedToolCount=len(application.dropped_tools),
        droppedTools=[dict(tool) for tool in application.dropped_tools],
    )


@router.get(
    "/v1/admin/settings/{key}",
    response_model=RuntimeSettingResponse,
    response_model_by_alias=True,
)
@router.get(
    "/api/admin/settings/{key}",
    response_model=RuntimeSettingResponse,
    response_model_by_alias=True,
)
async def get_runtime_setting(
    request: Request,
    key: str,
    principal: Annotated[AuthPrincipal, Depends(require_permission("settings:read"))],
    tenant_id: str = Query(default=GLOBAL_TENANT_ID, min_length=1, max_length=128),
) -> RuntimeSettingResponse:
    store = require_runtime_settings_store(request)
    record = await store.find(key, tenant_id=runtime_settings_tenant(principal, tenant_id))
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="runtime setting not found"
        )
    return runtime_setting_response(record)


@router.put(
    "/v1/admin/settings/{key}",
    response_model=RuntimeSettingUpdateResponse,
    response_model_by_alias=True,
)
@router.put(
    "/api/admin/settings/{key}",
    response_model=RuntimeSettingUpdateResponse,
    response_model_by_alias=True,
)
async def set_runtime_setting(
    request: Request,
    key: str,
    body: RuntimeSettingUpdateRequest,
    principal: Annotated[AuthPrincipal, Depends(require_permission("settings:write"))],
    tenant_id: str = Query(default=GLOBAL_TENANT_ID, min_length=1, max_length=128),
) -> RuntimeSettingUpdateResponse:
    store = require_runtime_settings_store(request)
    resolved_tenant_id = runtime_settings_tenant(principal, tenant_id)
    update = RuntimeSettingUpdate(
        tenant_id=resolved_tenant_id,
        key=key,
        value=body.value,
        value_type=body.type,
        category=body.category,
        description=body.description,
        updated_by=principal.user_id,
        metadata=body.metadata,
    )
    validate_runtime_setting_update(update)
    record = await store.set(update)
    return RuntimeSettingUpdateResponse(
        tenantId=record.tenant_id,
        key=record.key,
        value=record.value,
        status="updated",
    )


@router.delete("/v1/admin/settings/{key}", status_code=status.HTTP_204_NO_CONTENT)
@router.delete("/api/admin/settings/{key}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_runtime_setting(
    request: Request,
    key: str,
    principal: Annotated[AuthPrincipal, Depends(require_permission("settings:write"))],
    tenant_id: str = Query(default=GLOBAL_TENANT_ID, min_length=1, max_length=128),
) -> Response:
    store = require_runtime_settings_store(request)
    await store.delete(key, tenant_id=runtime_settings_tenant(principal, tenant_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/v1/admin/settings/refresh")
@router.post("/api/admin/settings/refresh")
async def refresh_runtime_settings_cache(
    _: Annotated[AuthPrincipal, Depends(require_permission("settings:write"))],
) -> dict[str, str]:
    return {"status": "cache_refreshed"}


def runtime_setting_response(record: RuntimeSettingRecord) -> RuntimeSettingResponse:
    return RuntimeSettingResponse(
        tenantId=record.tenant_id,
        key=record.key,
        value=record.value,
        type=record.value_type,
        category=record.category,
        description=record.description,
        updatedBy=record.updated_by,
        updatedAt=record.updated_at,
        metadata=dict(record.metadata),
    )


def validate_runtime_setting_update(update: RuntimeSettingUpdate) -> None:
    try:
        update.validate()
        if update.key == LANGCHAIN_MIDDLEWARE_POLICY_SETTING_KEY:
            value = runtime_setting_json_object(
                update, error_message="invalid langchain.middleware_policy"
            )
            if langchain_middleware_policy_from_mapping(value) is None:
                raise ValueError("invalid langchain.middleware_policy")
        if update.key == TOOL_PROFILE_BUDGET_SETTING_KEY:
            value = runtime_setting_json_object(
                update, error_message="invalid tools.profile_budget"
            )
            if tool_profile_budget_from_mapping(value) is None:
                raise ValueError("invalid tools.profile_budget")
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error


def runtime_setting_json_object(
    update: RuntimeSettingUpdate,
    *,
    error_message: str,
) -> Mapping[str, object]:
    value = runtime_setting_value(
        RuntimeSettingRecord(
            tenant_id=update.tenant_id,
            key=update.key,
            value=update.value,
            value_type=update.value_type,
            category=update.category,
            description=update.description,
            updated_by=update.updated_by,
            metadata=update.metadata,
        )
    )
    if not isinstance(value, Mapping):
        raise ValueError(error_message)
    return cast(Mapping[str, object], value)


LANGCHAIN_MIDDLEWARE_POLICY_SETTING_KEY = "langchain.middleware_policy"
TOOL_PROFILE_BUDGET_SETTING_KEY = "tools.profile_budget"


def langchain_middleware_policy_diagnostics(
    records: Sequence[RuntimeSettingRecord],
    *,
    tenant_id: str,
    settings: Settings,
    default_policy: LangChainMiddlewarePolicy,
) -> LangChainMiddlewarePolicyDiagnosticsResponse:
    record = effective_runtime_setting_record(
        records,
        tenant_id=tenant_id,
        key=LANGCHAIN_MIDDLEWARE_POLICY_SETTING_KEY,
    )
    if record is None:
        return LangChainMiddlewarePolicyDiagnosticsResponse(
            tenantId=tenant_id,
            key=LANGCHAIN_MIDDLEWARE_POLICY_SETTING_KEY,
            status="default",
            source="default",
            settingTenantId=None,
            policy=langchain_middleware_policy_response(default_policy),
            middlewareChain=langchain_middleware_chain_preview_response(
                build_langchain_agent_middleware(settings, policy=default_policy),
                interrupt_on_tools=[],
            ),
        )
    try:
        value = runtime_setting_value(record)
    except ValueError as error:
        return ignored_langchain_middleware_policy_response(
            tenant_id=tenant_id,
            record=record,
            reason=str(error),
        )
    if not isinstance(value, Mapping):
        return ignored_langchain_middleware_policy_response(
            tenant_id=tenant_id,
            record=record,
            reason="langchain.middleware_policy must be a JSON object",
        )
    policy = langchain_middleware_policy_from_mapping(cast(Mapping[str, object], value))
    if policy is None:
        return ignored_langchain_middleware_policy_response(
            tenant_id=tenant_id,
            record=record,
            reason="invalid langchain.middleware_policy",
        )
    return LangChainMiddlewarePolicyDiagnosticsResponse(
        tenantId=tenant_id,
        key=LANGCHAIN_MIDDLEWARE_POLICY_SETTING_KEY,
        status="applied",
        source=runtime_setting_source(record, tenant_id=tenant_id),
        settingTenantId=record.tenant_id,
        policy=langchain_middleware_policy_response(policy),
        middlewareChain=langchain_middleware_chain_preview_response(
            build_langchain_agent_middleware(settings, policy=policy),
            interrupt_on_tools=[],
        ),
    )


def effective_runtime_setting_record(
    records: Sequence[RuntimeSettingRecord],
    *,
    tenant_id: str,
    key: str,
) -> RuntimeSettingRecord | None:
    tenant_record: RuntimeSettingRecord | None = None
    global_record: RuntimeSettingRecord | None = None
    for record in records:
        if record.key != key:
            continue
        if record.tenant_id == tenant_id:
            tenant_record = record
        elif record.tenant_id == GLOBAL_TENANT_ID:
            global_record = record
    return tenant_record or global_record


def ignored_langchain_middleware_policy_response(
    *,
    tenant_id: str,
    record: RuntimeSettingRecord,
    reason: str,
) -> LangChainMiddlewarePolicyDiagnosticsResponse:
    return LangChainMiddlewarePolicyDiagnosticsResponse(
        tenantId=tenant_id,
        key=LANGCHAIN_MIDDLEWARE_POLICY_SETTING_KEY,
        status="ignored",
        source=runtime_setting_source(record, tenant_id=tenant_id),
        settingTenantId=record.tenant_id,
        reason=reason,
        policy=None,
    )


def runtime_setting_source(
    record: RuntimeSettingRecord,
    *,
    tenant_id: str,
) -> Literal["tenant_runtime_setting", "global_runtime_setting"]:
    if record.tenant_id == tenant_id:
        return "tenant_runtime_setting"
    return "global_runtime_setting"


def langchain_middleware_policy_response(
    policy: LangChainMiddlewarePolicy,
) -> LangChainMiddlewarePolicyResponse:
    return LangChainMiddlewarePolicyResponse(
        modelCallRunLimit=policy.model_call_run_limit,
        toolCallRunLimit=policy.tool_call_run_limit,
        modelRetryMaxRetries=policy.model_retry_max_retries,
        toolRetryMaxRetries=policy.tool_retry_max_retries,
        piiRules=[
            LangChainMiddlewarePiiRuleResponse(
                type=rule.pii_type,
                strategy=rule.strategy,
                applyToInput=rule.apply_to_input,
                applyToOutput=rule.apply_to_output,
                applyToToolResults=rule.apply_to_tool_results,
                applyToStreamOutput=rule.apply_to_stream_output,
            )
            for rule in policy.pii_rules
        ],
    )


def langchain_middleware_chain_preview_response(
    middleware: Sequence[object],
    *,
    interrupt_on_tools: Sequence[str],
) -> LangChainMiddlewareChainPreviewResponse:
    middleware_names = [type(item).__name__ for item in middleware]
    return LangChainMiddlewareChainPreviewResponse(
        status="applied",
        count=len(middleware_names),
        middleware=middleware_names,
        piiRuleCount=middleware_names.count("PIIMiddleware"),
        hitlToolCount=len(interrupt_on_tools),
        fallbackModelCount=middleware_names.count("ModelFallbackMiddleware"),
    )


def tool_profile_budget_diagnostics(
    records: Sequence[RuntimeSettingRecord],
    *,
    tenant_id: str,
    tools: Sequence[ToolSpec] | None = None,
) -> ToolProfileBudgetDiagnosticsResponse:
    record = effective_runtime_setting_record(
        records,
        tenant_id=tenant_id,
        key=TOOL_PROFILE_BUDGET_SETTING_KEY,
    )
    if record is None:
        return ToolProfileBudgetDiagnosticsResponse(
            tenantId=tenant_id,
            key=TOOL_PROFILE_BUDGET_SETTING_KEY,
            status="default",
            source="default",
            settingTenantId=None,
            reason="no additional tool profile budget",
            budget=None,
        )
    try:
        value = runtime_setting_value(record)
    except ValueError as error:
        return ignored_tool_profile_budget_response(
            tenant_id=tenant_id,
            record=record,
            reason=str(error),
        )
    budget = tool_profile_budget_from_mapping(value)
    if budget is None:
        return ignored_tool_profile_budget_response(
            tenant_id=tenant_id,
            record=record,
            reason="invalid tools.profile_budget",
        )
    application = apply_tool_profile_budget_with_evidence(tools or [], budget)
    return ToolProfileBudgetDiagnosticsResponse(
        tenantId=tenant_id,
        key=TOOL_PROFILE_BUDGET_SETTING_KEY,
        status="applied",
        source=runtime_setting_source(record, tenant_id=tenant_id),
        settingTenantId=record.tenant_id,
        budget=tool_profile_budget_response(budget),
        configuredToolCount=len(tools or []),
        activeToolCount=len(application.tools),
        activeTools=[tool.qualified_name for tool in application.tools],
        droppedToolCount=len(application.dropped_tools),
        droppedTools=[dict(item) for item in application.dropped_tools],
    )


def ignored_tool_profile_budget_response(
    *,
    tenant_id: str,
    record: RuntimeSettingRecord,
    reason: str,
) -> ToolProfileBudgetDiagnosticsResponse:
    return ToolProfileBudgetDiagnosticsResponse(
        tenantId=tenant_id,
        key=TOOL_PROFILE_BUDGET_SETTING_KEY,
        status="ignored",
        source=runtime_setting_source(record, tenant_id=tenant_id),
        settingTenantId=record.tenant_id,
        reason=reason,
        budget=None,
    )


def tool_profile_budget_response(budget: ToolProfileBudget) -> ToolProfileBudgetResponse:
    return ToolProfileBudgetResponse(
        maxTools=budget.max_tools,
        allowedRiskLevels=sorted(budget.allowed_risk_levels)
        if budget.allowed_risk_levels is not None
        else None,
        allowedTools=sorted(budget.allowed_tools) if budget.allowed_tools is not None else None,
        deniedTools=sorted(budget.denied_tools),
    )


def preview_tool_spec(
    tool: ToolProfileBudgetPreviewToolRequest,
    *,
    tenant_id: str,
) -> ToolSpec:
    namespace, _, name = tool.name.partition(":")
    if not namespace or not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid configured tool: name must be fully qualified",
        )
    return ToolSpec(
        tenant_id=tenant_id,
        namespace=namespace,
        name=name,
        description="Preview tool profile budget input.",
        risk_level=tool.risk_level,
        input_schema={"type": "object"},
        output_schema={"type": "object"},
    )


def runtime_settings_tenant(principal: AuthPrincipal, tenant_id: str | None) -> str:
    if tenant_id == GLOBAL_TENANT_ID:
        return GLOBAL_TENANT_ID
    return principal.tenant_id
