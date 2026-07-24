from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from shlex import quote
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from reactor.agents.graph import GraphProfileMetadata, research_plan_from_profile
from reactor.agents.langchain_middleware import (
    build_langchain_agent_middleware,
    default_langchain_middleware_policy,
    langchain_middleware_policy_metadata,
)
from reactor.agents.profiles import default_graph_profile_registry
from reactor.agents.runner import public_run_metadata, sanitize_public_metadata_value
from reactor.agents.streaming import replay_stream_events
from reactor.api.auth import principal_from_headers
from reactor.auth.rbac import AuthPrincipal
from reactor.core.container import AppContainer
from reactor.evals.hardening_suite import graph_topology_evidence
from reactor.kernel.ids import new_id
from reactor.observability.metrics import RUNS_CREATED
from reactor.observability.tracing import redact_trace_payload
from reactor.persistence.run_store import SessionRunRecord, SessionStore
from reactor.persistence.tool_invocation_store import (
    ToolInvocationRecord,
    validate_tool_invocation_status,
)
from reactor.prompts.profiles import resolve_tool_exposure
from reactor.response.structured import (
    context_manifest_citation_ids,
    context_manifest_requires_citations,
    merge_citation_response_schema,
)
from reactor.runs.lifecycle import RunLifecyclePublisher
from reactor.runs.service import (
    CHECKPOINT_PROVENANCE_METADATA_KEYS,
    IgnoredToolProfileBudget,
    ResolvedLangChainMiddlewarePolicy,
    ResolvedStructuredOutput,
    RunCancellationConflict,
    RunPreflightResult,
    RunService,
    RuntimeSettingsStore,
    ToolExposure,
    ToolSpecProvider,
    TrustedCheckpointFork,
    optional_metadata_json_object,
    resolved_structured_output,
)

router = APIRouter(prefix="/v1/runs", tags=["runs"])
APPLICATION_OWNED_RUN_METADATA_KEYS = frozenset({"contextManifest", "context_manifest"})


class CreateRunRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10_000)
    thread_id: str | None = Field(default=None, alias="threadId", min_length=1, max_length=128)
    checkpoint_ns: str | None = Field(
        default=None,
        alias="checkpointNs",
        min_length=1,
        max_length=128,
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunPreflightRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10_000)
    thread_id: str | None = Field(default=None, alias="threadId", min_length=1, max_length=128)
    checkpoint_ns: str | None = Field(
        default=None,
        alias="checkpointNs",
        min_length=1,
        max_length=128,
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunEventResponse(BaseModel):
    sequence: int
    event_type: str
    payload: dict[str, object]


class RunDetailResponse(BaseModel):
    run_id: str
    tenant_id: str
    user_id: str
    thread_id: str
    checkpoint_ns: str
    last_checkpoint_id: str | None = None
    status: str
    input_text: str
    response_text: str | None
    created_at: str
    updated_at: str
    metadata: dict[str, object]
    next_actions: list[RunOperatorNextAction] = Field(alias="nextActions")


class ToolInvocationExecutionResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    risk_level: str | None = Field(default=None, alias="riskLevel")
    approval_required: bool | None = Field(default=None, alias="approvalRequired")
    cache_status: str | None = Field(default=None, alias="cacheStatus")
    executed: bool | None = None


class RunToolInvocationResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    run_id: str = Field(alias="runId")
    tool_id: str = Field(alias="toolId")
    status: str
    success: bool
    approval_id: str | None = Field(default=None, alias="approvalId")
    idempotency_key: str = Field(alias="idempotencyKey")
    request_checksum: str = Field(alias="requestChecksum")
    result_checksum: str | None = Field(default=None, alias="resultChecksum")
    execution: ToolInvocationExecutionResponse
    input: dict[str, object]
    output: dict[str, object] | None
    error: dict[str, object] | None
    started_at: datetime = Field(alias="startedAt")
    completed_at: datetime | None = Field(default=None, alias="completedAt")
    duration_ms: int | None = Field(default=None, alias="durationMs")


class StructuredOutputDiagnosticsRequest(BaseModel):
    metadata: dict[str, Any] = Field(default_factory=dict)


class StructuredOutputDiagnosticsResponse(BaseModel):
    status: str
    format: str
    strategy: str
    enforcement: str
    response_format_mode: str = Field(alias="responseFormatMode")
    fallback_reason: str | None = Field(default=None, alias="fallbackReason")
    schema_source: str | None = Field(default=None, alias="schemaSource")
    output_schema: dict[str, object] | None = Field(default=None, alias="schema")
    ignored_schema: dict[str, object] | None = Field(default=None, alias="ignoredSchema")
    ignored_format: dict[str, object] | None = Field(default=None, alias="ignoredFormat")
    citation_boundary: dict[str, object] | None = Field(default=None, alias="citationBoundary")


class RunPreflightResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    status: str
    tenant_id: str
    user_id: str
    runtime: str
    thread_id: str
    checkpoint_ns: str
    model: dict[str, object]
    middleware_policy: dict[str, object] = Field(alias="middlewarePolicy")
    middleware_chain: dict[str, object] = Field(alias="middlewareChain")
    tool_profile_budget: dict[str, object] = Field(alias="toolProfileBudget")
    structured_output: StructuredOutputDiagnosticsResponse = Field(alias="structuredOutput")
    graph_topology: dict[str, object] = Field(alias="graphTopology")
    research_plan: dict[str, object] | None = Field(default=None, alias="researchPlan")
    checkpoint_replay: dict[str, object] | None = Field(
        default=None,
        alias="checkpointReplay",
    )


class ForkRunRequest(BaseModel):
    message: str | None = Field(default=None, min_length=1, max_length=10_000)
    thread_id: str | None = Field(default=None, alias="threadId", min_length=1, max_length=128)
    checkpoint_ns: str | None = Field(
        default=None,
        alias="checkpointNs",
        min_length=1,
        max_length=128,
    )
    checkpoint_id: str | None = Field(
        default=None,
        alias="checkpointId",
        min_length=1,
        max_length=256,
    )
    metadata: dict[str, Any] | None = None


class ForkRunProvenance(BaseModel):
    source: str
    forked_from_run_id: str
    forked_from_thread_id: str
    forked_from_checkpoint_ns: str
    forked_from_checkpoint_id: str | None = None
    fork_target_thread_id: str
    fork_target_checkpoint_ns: str


class RunOperatorNextAction(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    label: str
    command: str
    source_run_id: str | None = Field(
        default=None, alias="sourceRunId", exclude_if=lambda v: v is None
    )
    thread_id: str | None = Field(default=None, alias="threadId", exclude_if=lambda v: v is None)
    checkpoint_ns: str | None = Field(
        default=None, alias="checkpointNs", exclude_if=lambda v: v is None
    )
    checkpoint_id: str | None = Field(
        default=None, alias="checkpointId", exclude_if=lambda v: v is None
    )
    approval_id: str | None = Field(
        default=None, alias="approvalId", exclude_if=lambda v: v is None
    )


class RunResponse(BaseModel):
    run_id: str
    status: str
    response: str
    metadata: dict[str, object] = Field(default_factory=dict)


class RunOperationResponse(RunResponse):
    next_actions: list[RunOperatorNextAction] = Field(alias="nextActions")


class ForkRunResponse(BaseModel):
    run_id: str
    source_run_id: str
    thread_id: str
    checkpoint_ns: str
    status: str
    response: str
    provenance: ForkRunProvenance
    next_actions: list[RunOperatorNextAction] = Field(alias="nextActions")


class ResumeRunRequest(BaseModel):
    approval_id: str = Field(alias="approvalId", min_length=1, max_length=128)
    approved: bool = Field(strict=True)
    reason: str | None = Field(default=None, min_length=1, max_length=1_000)


class CancelRunRequest(BaseModel):
    reason: str | None = Field(default=None, min_length=1, max_length=1_000)


def get_container(request: Request) -> AppContainer:
    return cast(AppContainer, request.app.state.reactor)


def get_run_lifecycle_publisher(container: object) -> RunLifecyclePublisher | None:
    accessor = getattr(container, "run_lifecycle_publisher", None)
    if accessor is None:
        return None
    return cast(RunLifecyclePublisher | None, accessor())


def get_runtime_settings_store(container: object) -> RuntimeSettingsStore | None:
    accessor = getattr(container, "runtime_settings_store", None)
    if accessor is None:
        return None
    return cast(RuntimeSettingsStore | None, accessor())


def get_tool_provider(container: object) -> ToolSpecProvider | None:
    accessor = getattr(container, "tool_store", None)
    if accessor is None:
        return None
    return cast(ToolSpecProvider | None, accessor())


def get_usage_ledger(container: object) -> object | None:
    accessor = getattr(container, "usage_ledger", None)
    if accessor is None:
        return None
    return accessor()


def build_run_service(container: AppContainer, run_store: object | None = None) -> RunService:
    return RunService(
        container.settings,
        cast(Any, run_store if run_store is not None else container.run_store()),
        container.graph,
        usage_ledger=get_usage_ledger(container),
        checkpointer=getattr(container, "checkpointer", None),
        graph_store=getattr(container, "graph_store", None),
        tool_provider=get_tool_provider(container),
        tool_handler=getattr(container, "agent_tool_handler", lambda: None)(),
        tool_invocation_store=getattr(container, "tool_invocation_store", lambda: None)(),
        builtin_tool_specs=getattr(container, "builtin_tool_specs", None),
        run_lifecycle_publisher=get_run_lifecycle_publisher(container),
        runtime_settings_store=get_runtime_settings_store(container),
        approval_store=getattr(container, "approval_store", lambda: None)(),
    )


def preflight_middleware_policy_metadata(
    container: AppContainer,
    result: RunPreflightResult,
) -> dict[str, object]:
    if result.runtime != "langchain_agent":
        return {
            "status": "not_applicable",
            "reason": "runtime does not use LangChain agent middleware",
        }
    if isinstance(result.middleware_policy, ResolvedLangChainMiddlewarePolicy):
        return result.middleware_policy.metadata()
    if result.middleware_policy is not None:
        return result.middleware_policy.metadata()
    policy = default_langchain_middleware_policy(container.settings)
    return {
        "status": "default",
        "source": "default",
        "policy": langchain_middleware_policy_metadata(policy),
    }


def preflight_middleware_chain_metadata(
    container: AppContainer,
    result: RunPreflightResult,
) -> dict[str, object]:
    if result.runtime != "langchain_agent":
        return {
            "status": "not_applicable",
            "count": 0,
            "middleware": [],
            "piiRuleCount": 0,
            "hitlToolCount": 0,
            "fallbackModelCount": 0,
        }
    policy = (
        result.middleware_policy.policy
        if isinstance(result.middleware_policy, ResolvedLangChainMiddlewarePolicy)
        else default_langchain_middleware_policy(container.settings)
    )
    interrupt_on_tools = [
        tool.qualified_name for tool in result.tool_exposure.tools or [] if tool.approval_required
    ]
    middleware = build_langchain_agent_middleware(
        container.settings,
        policy=policy,
        interrupt_on_tools=interrupt_on_tools,
    )
    names = [type(item).__name__ for item in middleware]
    return {
        "status": "applied",
        "count": len(names),
        "middleware": names,
        "piiRuleCount": names.count("PIIMiddleware"),
        "hitlToolCount": len(interrupt_on_tools),
        "fallbackModelCount": names.count("ModelFallbackMiddleware"),
    }


def preflight_tool_profile_budget_metadata(tool_exposure: ToolExposure) -> dict[str, object]:
    metadata = tool_exposure.resolved_budget_metadata()
    if metadata is not None:
        status = (
            "ignored"
            if isinstance(tool_exposure.resolved_budget, IgnoredToolProfileBudget)
            else "applied"
        )
        return {"status": status, **metadata}
    return {
        "status": "default",
        "source": "default",
        "configuredToolCount": tool_exposure.configured_tool_count,
        "activeToolCount": tool_exposure.active_tool_count,
        "activeTools": list(tool_exposure.active_tools),
        "droppedToolCount": 0,
        "droppedTools": [],
    }


def preflight_research_plan(
    result: RunPreflightResult,
    message: str,
) -> dict[str, object] | None:
    graph_profile = result.metadata.get("graphProfile")
    if graph_profile != "research":
        return None
    profile = default_graph_profile_registry().get("research")
    try:
        tool_exposure = resolve_tool_exposure(
            profile_tools=profile.tool_allowlist,
            request_tools=list(result.tool_exposure.active_tools),
            policy=profile.tool_forcing_policy,
        )
    except ValueError:
        return blocked_research_preflight_plan(profile_id="research", message=message)
    plan = research_plan_from_profile(
        GraphProfileMetadata(
            graph_profile="research",
            prompt_version=profile.prompt_version,
            model_provider=profile.model_provider,
            selected_model=profile.model,
            checkpoint_ns=profile.checkpoint_ns,
            temperature=profile.temperature,
            max_tool_calls=profile.max_tool_calls,
            active_tools=tool_exposure.active_tools,
            tool_choice=tool_exposure.tool_choice,
            tool_profile_budget=result.tool_exposure.resolved_budget_metadata(),
        ),
        message,
    )
    if plan is None:
        return None
    return plan


def preflight_checkpoint_replay_metadata(result: RunPreflightResult) -> dict[str, object]:
    if result.checkpoint_replay.metadata is not None:
        return {
            **result.checkpoint_replay.metadata,
            "checkpointPinned": result.checkpoint_replay.checkpoint_id is not None,
        }
    return {
        "status": "default",
        "source": "default",
        "targetThreadId": result.thread_id,
        "targetCheckpointNs": result.checkpoint_ns,
        "checkpointPinned": False,
    }


def blocked_research_preflight_plan(*, profile_id: str, message: str) -> dict[str, object]:
    return {
        "status": "blocked",
        "profile": profile_id,
        "question": message,
        "reason": "forced_tool_unavailable",
        "missingTool": "Rag:hybrid_search",
        "operatorAction": "allow_required_research_tool",
        "recoverySteps": [
            "remove_forced_tool_from_denied_tools",
            "allow_read_risk_tools_for_research_profile",
            "rerun_preflight_before_starting_research_run",
        ],
    }


def preflight_status(result: RunPreflightResult, research_plan: dict[str, object] | None) -> str:
    if research_plan is not None and research_plan.get("status") == "blocked":
        return "rejected"
    return result.status


@router.post("", response_model=RunOperationResponse, response_model_exclude_none=True)
async def create_run(
    request: Request,
    body: CreateRunRequest,
    principal: Annotated[AuthPrincipal, Depends(principal_from_headers)],
) -> RunOperationResponse:
    container = get_container(request)
    service = build_run_service(container)
    result = await service.create_run(
        body.message,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        trusted_user_groups=principal.groups,
        thread_id=body.thread_id,
        checkpoint_ns=body.checkpoint_ns,
        metadata=public_run_request_metadata(body.metadata),
    )
    RUNS_CREATED.labels(status=result.status).inc()
    return RunOperationResponse(
        **result.as_response(),
        nextActions=run_operator_next_actions(
            result.run_id,
            run_status=result.status,
            thread_id=result.thread_id,
            checkpoint_ns=result.checkpoint_ns,
        ),
    )


@router.post(
    "/preflight",
    response_model=RunPreflightResponse,
    response_model_by_alias=True,
    response_model_exclude_none=True,
)
async def preflight_run(
    request: Request,
    body: RunPreflightRequest,
    principal: Annotated[AuthPrincipal, Depends(principal_from_headers)],
) -> RunPreflightResponse:
    container = get_container(request)
    result = await build_run_service(container).preflight_run(
        body.message,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        thread_id=body.thread_id,
        checkpoint_ns=body.checkpoint_ns,
        metadata=public_run_request_metadata(body.metadata),
    )
    research_plan = preflight_research_plan(result, body.message)
    return RunPreflightResponse(
        status=preflight_status(result, research_plan),
        tenant_id=result.tenant_id,
        user_id=result.user_id,
        runtime=result.runtime,
        thread_id=result.thread_id,
        checkpoint_ns=result.checkpoint_ns,
        model={"provider": result.provider, "name": result.model},
        middlewarePolicy=preflight_middleware_policy_metadata(container, result),
        middlewareChain=preflight_middleware_chain_metadata(container, result),
        toolProfileBudget=preflight_tool_profile_budget_metadata(result.tool_exposure),
        structuredOutput=structured_output_diagnostics_response(
            result.structured_output,
            context_manifest=optional_metadata_json_object(result.metadata.get("contextManifest")),
        ),
        graphTopology=graph_topology_evidence(),
        researchPlan=research_plan,
        checkpointReplay=preflight_checkpoint_replay_metadata(result),
    )


@router.post(
    "/structured-output/diagnostics",
    response_model=StructuredOutputDiagnosticsResponse,
    response_model_by_alias=True,
    response_model_exclude_none=True,
)
async def diagnose_structured_output(
    body: StructuredOutputDiagnosticsRequest,
) -> StructuredOutputDiagnosticsResponse:
    return structured_output_diagnostics_response(
        resolved_structured_output(body.metadata),
        context_manifest=optional_metadata_json_object(body.metadata.get("contextManifest")),
    )


@router.get("/{run_id}", response_model=RunDetailResponse, response_model_exclude_none=True)
async def get_run(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(principal_from_headers)],
    run_id: str,
) -> RunDetailResponse:
    container = get_container(request)
    run_store = container.run_store()
    if run_store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="run persistence is not configured",
        )

    run = await require_run_access(
        cast(SessionStore, run_store), run_id=run_id, principal=principal
    )
    return run_detail_response(run)


@router.get("/{run_id}/events", response_model=list[RunEventResponse])
async def list_run_events(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(principal_from_headers)],
    run_id: str,
    after_sequence: int = Query(default=0, ge=0),
) -> list[RunEventResponse]:
    container = get_container(request)
    run_store = container.run_store()
    if run_store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="run event persistence is not configured",
        )

    await require_run_access(cast(SessionStore, run_store), run_id=run_id, principal=principal)
    service = build_run_service(container, run_store)
    events = await service.list_events(
        run_id,
        tenant_id=principal.tenant_id,
        after_sequence=after_sequence,
    )
    return [
        RunEventResponse(
            sequence=event.sequence,
            event_type=event.event_type,
            payload=public_run_event_payload(event.payload),
        )
        for event in events
    ]


@router.get(
    "/{run_id}/tool-invocations",
    response_model=list[RunToolInvocationResponse],
    response_model_by_alias=True,
)
async def list_run_tool_invocations(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(principal_from_headers)],
    run_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    status_filter_param: str | None = Query(default=None, alias="status"),
) -> list[RunToolInvocationResponse]:
    status_filter = parse_tool_invocation_status_filter(status_filter_param)
    container = get_container(request)
    run_store = container.run_store()
    if run_store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="run persistence is not configured",
        )
    run = await require_run_access(
        cast(SessionStore, run_store),
        run_id=run_id,
        principal=principal,
    )
    store_accessor = getattr(container, "tool_invocation_store", None)
    tool_invocation_store = store_accessor() if store_accessor is not None else None
    if tool_invocation_store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="tool invocation persistence is not configured",
        )
    records = await tool_invocation_store.list_for_run(
        tenant_id=principal.tenant_id,
        run_id=run.run_id,
        limit=limit,
        status=status_filter,
    )
    return [run_tool_invocation_response(record) for record in records]


@router.get("/{run_id}/stream-events", response_model=list[RunEventResponse])
async def list_run_stream_events(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(principal_from_headers)],
    run_id: str,
    after_sequence: int = Query(default=0, ge=0),
    event_type: str | None = Query(default=None, min_length=1, max_length=128),
) -> list[RunEventResponse]:
    container = get_container(request)
    run_store = container.run_store()
    if run_store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="run event persistence is not configured",
        )

    await require_run_access(cast(SessionStore, run_store), run_id=run_id, principal=principal)
    service = build_run_service(container, run_store)
    persisted_events = await service.list_events(
        run_id,
        tenant_id=principal.tenant_id,
        after_sequence=after_sequence,
    )
    events = replay_stream_events(persisted_events, after_sequence=after_sequence)
    if event_type is not None:
        events = [event for event in events if event.event_type == event_type]
    return [
        RunEventResponse(
            sequence=event.sequence,
            event_type=event.event_type,
            payload=public_run_event_payload(event.payload),
        )
        for event in events
    ]


@router.post("/{run_id}/fork", response_model=ForkRunResponse)
async def fork_run(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(principal_from_headers)],
    run_id: str,
    body: ForkRunRequest,
) -> ForkRunResponse:
    container = get_container(request)
    run_store = container.run_store()
    if run_store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="run persistence is not configured",
        )

    source_run = await require_run_access(
        cast(SessionStore, run_store),
        run_id=run_id,
        principal=principal,
    )
    fork_thread_id = body.thread_id or new_id("thread")
    fork_checkpoint_ns = body.checkpoint_ns or source_run.checkpoint_ns
    fork_metadata = fork_run_metadata(
        source_run,
        body,
        target_thread_id=fork_thread_id,
        target_checkpoint_ns=fork_checkpoint_ns,
    )
    checkpoint_fork = trusted_checkpoint_fork(
        source_run,
        body,
        target_thread_id=fork_thread_id,
        target_checkpoint_ns=fork_checkpoint_ns,
    )
    service = build_run_service(container, run_store)
    result = await service.create_run(
        body.message or source_run.input_text,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        trusted_user_groups=principal.groups,
        thread_id=fork_thread_id,
        checkpoint_ns=fork_checkpoint_ns,
        metadata=fork_metadata,
        checkpoint_fork=checkpoint_fork,
    )
    RUNS_CREATED.labels(status=result.status).inc()
    return ForkRunResponse(
        run_id=result.run_id,
        source_run_id=source_run.run_id,
        thread_id=result.thread_id,
        checkpoint_ns=result.checkpoint_ns,
        status=result.status,
        response=result.response,
        provenance=fork_run_provenance(
            source_run,
            body,
            target_thread_id=fork_thread_id,
            target_checkpoint_ns=fork_checkpoint_ns,
        ),
        nextActions=fork_run_next_actions(
            result.run_id,
            run_status=result.status,
            thread_id=result.thread_id,
            checkpoint_ns=result.checkpoint_ns,
        ),
    )


@router.post(
    "/{run_id}/resume", response_model=RunOperationResponse, response_model_exclude_none=True
)
async def resume_run(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(principal_from_headers)],
    run_id: str,
    body: ResumeRunRequest,
) -> RunOperationResponse:
    container = get_container(request)
    run_store = container.run_store()
    if run_store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="run persistence is not configured",
        )

    run = await require_run_access(
        cast(SessionStore, run_store), run_id=run_id, principal=principal
    )
    service = build_run_service(container, run_store)
    result = await service.resume_run(
        run_id=run_id,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        thread_id=run.thread_id,
        checkpoint_ns=run.checkpoint_ns,
        approval_id=body.approval_id,
        approved=body.approved,
        reason=body.reason,
        run_metadata=run.metadata,
        input_text=run.input_text,
        run_user_id=run.user_id,
        run_status=run.status,
    )
    return RunOperationResponse(
        **result.as_response(),
        nextActions=run_operator_next_actions(
            result.run_id,
            run_status=result.status,
            thread_id=run.thread_id,
            checkpoint_ns=run.checkpoint_ns,
            checkpoint_id=source_run_persisted_checkpoint_id(run),
        ),
    )


@router.post(
    "/{run_id}/cancel", response_model=RunOperationResponse, response_model_exclude_none=True
)
async def cancel_run(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(principal_from_headers)],
    run_id: str,
    body: CancelRunRequest,
) -> RunOperationResponse:
    container = get_container(request)
    run_store = container.run_store()
    if run_store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="run persistence is not configured",
        )

    run = await require_run_access(
        cast(SessionStore, run_store), run_id=run_id, principal=principal
    )
    service = build_run_service(container, run_store)
    try:
        result = await service.cancel_run(
            run_id=run_id,
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            thread_id=run.thread_id,
            checkpoint_ns=run.checkpoint_ns,
            reason=body.reason,
        )
    except RunCancellationConflict as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="run is not running",
        ) from error
    return RunOperationResponse(
        **result.as_response(),
        nextActions=run_operator_next_actions(
            result.run_id,
            run_status=result.status,
            thread_id=run.thread_id,
            checkpoint_ns=run.checkpoint_ns,
            checkpoint_id=source_run_persisted_checkpoint_id(run),
        ),
    )


def fork_run_metadata(
    source_run: SessionRunRecord,
    body: ForkRunRequest,
    *,
    target_thread_id: str,
    target_checkpoint_ns: str,
) -> dict[str, Any]:
    provenance = fork_run_provenance(
        source_run,
        body,
        target_thread_id=target_thread_id,
        target_checkpoint_ns=target_checkpoint_ns,
    )
    metadata = {
        **without_fork_provenance_metadata(source_run.metadata),
        **without_fork_provenance_metadata(body.metadata or {}),
        "source": provenance.source,
        "forkedFromRunId": provenance.forked_from_run_id,
        "forkedFromThreadId": provenance.forked_from_thread_id,
        "forkedFromCheckpointNs": provenance.forked_from_checkpoint_ns,
        "forkTargetThreadId": provenance.fork_target_thread_id,
        "forkTargetCheckpointNs": provenance.fork_target_checkpoint_ns,
    }
    if provenance.forked_from_checkpoint_id is not None:
        metadata["forkedFromCheckpointId"] = provenance.forked_from_checkpoint_id
    return metadata


FORK_PROVENANCE_METADATA_KEYS = CHECKPOINT_PROVENANCE_METADATA_KEYS


def public_run_request_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in dict(metadata).items()
        if key not in APPLICATION_OWNED_RUN_METADATA_KEYS
    }


def without_fork_provenance_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in dict(metadata).items()
        if key not in FORK_PROVENANCE_METADATA_KEYS
        and key not in APPLICATION_OWNED_RUN_METADATA_KEYS
    }


def fork_run_provenance(
    source_run: SessionRunRecord,
    body: ForkRunRequest,
    *,
    target_thread_id: str,
    target_checkpoint_ns: str,
) -> ForkRunProvenance:
    requested_checkpoint_id = body.checkpoint_id.strip() if body.checkpoint_id else None
    return ForkRunProvenance(
        source="checkpoint_fork",
        forked_from_run_id=source_run.run_id,
        forked_from_thread_id=source_run.thread_id,
        forked_from_checkpoint_ns=source_run.checkpoint_ns,
        forked_from_checkpoint_id=requested_checkpoint_id
        or source_run_persisted_checkpoint_id(source_run),
        fork_target_thread_id=target_thread_id,
        fork_target_checkpoint_ns=target_checkpoint_ns,
    )


def trusted_checkpoint_fork(
    source_run: SessionRunRecord,
    body: ForkRunRequest,
    *,
    target_thread_id: str,
    target_checkpoint_ns: str,
) -> TrustedCheckpointFork:
    provenance = fork_run_provenance(
        source_run,
        body,
        target_thread_id=target_thread_id,
        target_checkpoint_ns=target_checkpoint_ns,
    )
    source_runtime_value = source_run.metadata.get("runtime")
    source_runtime = (
        source_runtime_value.strip()
        if isinstance(source_runtime_value, str) and source_runtime_value.strip()
        else "langgraph"
    )
    source_graph_profile_value = source_run.metadata.get("graphProfile")
    source_graph_profile = (
        source_graph_profile_value.strip()
        if isinstance(source_graph_profile_value, str) and source_graph_profile_value.strip()
        else None
    )
    return TrustedCheckpointFork(
        source_run_id=provenance.forked_from_run_id,
        source_thread_id=provenance.forked_from_thread_id,
        source_checkpoint_ns=provenance.forked_from_checkpoint_ns,
        source_checkpoint_id=provenance.forked_from_checkpoint_id,
        source_runtime=source_runtime,
        source_graph_profile=source_graph_profile,
        target_thread_id=provenance.fork_target_thread_id,
        target_checkpoint_ns=provenance.fork_target_checkpoint_ns,
    )


def fork_run_next_actions(
    run_id: str,
    *,
    run_status: str | None = None,
    thread_id: str | None = None,
    checkpoint_ns: str | None = None,
) -> list[RunOperatorNextAction]:
    return run_operator_next_actions(
        run_id,
        subject="forked run",
        run_status=run_status,
        thread_id=thread_id,
        checkpoint_ns=checkpoint_ns,
    )


def run_operator_next_actions(
    run_id: str,
    *,
    subject: str = "run",
    run_status: str | None = None,
    thread_id: str | None = None,
    checkpoint_ns: str | None = None,
    checkpoint_id: str | None = None,
) -> list[RunOperatorNextAction]:
    quoted_run_id = quote(run_id)
    action_metadata = {
        "sourceRunId": run_id,
        "threadId": thread_id,
        "checkpointNs": checkpoint_ns,
        "checkpointId": checkpoint_id,
    }
    actions = [
        RunOperatorNextAction(
            id="diagnose-run",
            label=f"Diagnose the {subject}",
            command=f"reactor-runs diagnose {quoted_run_id} --output table",
            **action_metadata,
        ),
        RunOperatorNextAction(
            id="inspect-state-history",
            label=f"Inspect the {subject}'s LangGraph checkpoint state history",
            command=f"reactor-admin state-history {quoted_run_id} --output table",
            **action_metadata,
        ),
        RunOperatorNextAction(
            id="replay-stream",
            label=f"Replay the {subject}'s persisted stream events",
            command=f"reactor-runs replay {quoted_run_id} --output table",
            **action_metadata,
        ),
    ]
    if (
        checkpoint_ns is not None
        and checkpoint_id is not None
        and run_status in {"completed", "succeeded", "failed", "error", "cancelled"}
    ):
        quoted_checkpoint_ns = quote(checkpoint_ns)
        quoted_checkpoint_id = quote(checkpoint_id)
        actions.append(
            RunOperatorNextAction(
                id="fork-checkpoint",
                label=f"Fork the {subject} from its latest LangGraph checkpoint",
                command=(
                    f"reactor-runs fork {quoted_run_id} --checkpoint-ns {quoted_checkpoint_ns} "
                    f"--checkpoint-id {quoted_checkpoint_id} --output table"
                ),
                sourceRunId=run_id,
                threadId=thread_id,
                checkpointNs=checkpoint_ns,
                checkpointId=checkpoint_id,
            )
        )
    if run_status == "started":
        actions.append(
            RunOperatorNextAction(
                id="cancel-run",
                label=f"Cancel the {subject}",
                command=(
                    f"reactor-runs cancel {quoted_run_id} "
                    "--reason 'operator requested cancellation' --output table"
                ),
                sourceRunId=run_id,
                threadId=thread_id,
                checkpointNs=checkpoint_ns,
            )
        )
    return actions


def source_run_persisted_checkpoint_id(source_run: SessionRunRecord) -> str | None:
    value = source_run.metadata.get("last_checkpoint_id")
    return value.strip() if isinstance(value, str) and value.strip() else None


async def require_run_access(
    run_store: SessionStore,
    *,
    run_id: str,
    principal: AuthPrincipal,
) -> SessionRunRecord:
    run = await run_store.find_session(run_id=run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    if run.tenant_id != principal.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to run")
    if run.user_id != principal.user_id and not principal.is_any_admin():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to run")
    return run


def run_detail_response(run: SessionRunRecord) -> RunDetailResponse:
    last_checkpoint_id = source_run_persisted_checkpoint_id(run)
    return RunDetailResponse(
        run_id=run.run_id,
        tenant_id=run.tenant_id,
        user_id=run.user_id,
        thread_id=run.thread_id,
        checkpoint_ns=run.checkpoint_ns,
        last_checkpoint_id=last_checkpoint_id,
        status=run.status,
        input_text=run.input_text,
        response_text=run.response_text,
        created_at=run.created_at,
        updated_at=run.updated_at,
        metadata=public_run_metadata(run.metadata),
        nextActions=run_operator_next_actions(
            run.run_id,
            run_status=run.status,
            thread_id=run.thread_id,
            checkpoint_ns=run.checkpoint_ns,
            checkpoint_id=last_checkpoint_id,
        ),
    )


def run_tool_invocation_response(record: ToolInvocationRecord) -> RunToolInvocationResponse:
    execution_metadata = tool_invocation_execution_metadata(record.input_payload)
    return RunToolInvocationResponse.model_validate(
        {
            "id": record.id,
            "runId": record.run_id,
            "toolId": record.tool_id,
            "status": record.status,
            "success": record.status in {"succeeded", "completed", "ok"},
            "approvalId": record.approval_id,
            "idempotencyKey": record.idempotency_key,
            "requestChecksum": record.request_checksum,
            "resultChecksum": record.result_checksum,
            "execution": ToolInvocationExecutionResponse.model_validate(
                {
                    "riskLevel": optional_string(execution_metadata.get("riskLevel")),
                    "approvalRequired": optional_bool(execution_metadata.get("approvalRequired")),
                    "cacheStatus": optional_string(execution_metadata.get("cacheStatus")),
                    "executed": optional_bool(execution_metadata.get("executed")),
                }
            ),
            "input": sanitized_tool_invocation_payload(record.input_payload),
            "output": sanitized_tool_invocation_output(
                record.output_payload,
                execution_metadata=execution_metadata,
            ),
            "error": sanitized_tool_invocation_error(
                record.error_payload,
                execution_metadata=execution_metadata,
            ),
            "startedAt": record.started_at,
            "completedAt": record.completed_at,
            "durationMs": duration_ms(record.started_at, record.completed_at),
        }
    )


def parse_tool_invocation_status_filter(raw_status: str | None) -> str | None:
    if raw_status is None or not raw_status.strip():
        return None
    try:
        return validate_tool_invocation_status(raw_status)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error


def tool_invocation_execution_metadata(payload: Mapping[str, Any]) -> Mapping[str, object]:
    return {
        "riskLevel": payload.get("riskLevel"),
        "approvalRequired": payload.get("approvalRequired"),
        "cacheStatus": payload.get("cacheStatus"),
        "executed": payload.get("executed"),
    }


def sanitized_tool_invocation_payload(payload: Mapping[str, Any]) -> dict[str, object]:
    raw_payload = payload.get("payload")
    if isinstance(raw_payload, Mapping):
        if high_risk_tool_execution(tool_invocation_execution_metadata(payload)):
            return {"payloadPresent": True}
        return sanitized_mapping(cast(Mapping[str, Any], raw_payload))
    return sanitized_mapping(payload)


def sanitized_optional_mapping(payload: Mapping[str, Any] | None) -> dict[str, object] | None:
    if payload is None:
        return None
    return sanitized_mapping(payload)


def sanitized_tool_invocation_output(
    payload: Mapping[str, Any] | None,
    *,
    execution_metadata: Mapping[str, object],
) -> dict[str, object] | None:
    if payload is None:
        return None
    if high_risk_tool_execution(execution_metadata):
        return {"payloadPresent": True}
    return sanitized_mapping(payload)


def sanitized_tool_invocation_error(
    payload: Mapping[str, Any] | None,
    *,
    execution_metadata: Mapping[str, object],
) -> dict[str, object] | None:
    if payload is None:
        return None
    sanitized = sanitized_mapping(payload)
    if high_risk_tool_execution(execution_metadata):
        return redact_error_messages(sanitized)
    return sanitized


def high_risk_tool_execution(execution_metadata: Mapping[str, object]) -> bool:
    return (
        execution_metadata.get("approvalRequired") is True
        or execution_metadata.get("riskLevel") != "read"
    )


def redact_error_messages(payload: Mapping[str, object]) -> dict[str, object]:
    redacted: dict[str, object] = {}
    for key, value in payload.items():
        if key == "message" and isinstance(value, str) and value.strip():
            redacted["messagePresent"] = True
        elif isinstance(value, Mapping):
            redacted[key] = redact_error_messages(cast(Mapping[str, object], value))
        elif isinstance(value, list):
            redacted[key] = [redact_error_message_value(item) for item in cast(list[object], value)]
        else:
            redacted[key] = value
    return redacted


def redact_error_message_value(value: object) -> object:
    if isinstance(value, Mapping):
        return redact_error_messages(cast(Mapping[str, object], value))
    return value


def sanitized_mapping(payload: Mapping[str, Any]) -> dict[str, object]:
    sanitized = sanitize_public_metadata_value(payload)
    sanitized = redact_trace_payload(sanitized)
    if isinstance(sanitized, dict):
        return cast(dict[str, object], sanitized)
    return {}


def optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def optional_bool(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def duration_ms(started_at: datetime, completed_at: datetime | None) -> int | None:
    if completed_at is None:
        return None
    return max(0, round((completed_at - started_at).total_seconds() * 1000))


def structured_output_diagnostics_response(
    structured_output: ResolvedStructuredOutput,
    *,
    context_manifest: Mapping[str, object] | None = None,
) -> StructuredOutputDiagnosticsResponse:
    metadata = structured_output.metadata()
    if metadata is None:
        metadata = {
            "format": "TEXT",
            "strategy": "reactor_boundary",
            "enforcement": "langchain_response_format_and_reactor_boundary",
        }
    ignored_schema = metadata.get("ignoredSchema")
    ignored_format = metadata.get("ignoredFormat")
    status_value = (
        "ignored"
        if isinstance(ignored_schema, Mapping) or isinstance(ignored_format, Mapping)
        else "applied"
    )
    if (
        status_value != "ignored"
        and metadata["format"] == "TEXT"
        and metadata["strategy"] == "reactor_boundary"
    ):
        status_value = "default"
    schema = metadata.get("schema")
    if isinstance(schema, Mapping):
        schema = merge_citation_response_schema(
            cast(Mapping[str, object], schema),
            context_manifest,
        )
    elif metadata["strategy"] == "json_object_schema" and context_manifest_requires_citations(
        context_manifest
    ):
        schema = merge_citation_response_schema(None, context_manifest)
    schema_source = metadata.get("schemaSource")
    citation_boundary = structured_output_citation_boundary(context_manifest)
    fallback_reason = None
    if isinstance(ignored_schema, Mapping):
        ignored_schema_mapping = cast(Mapping[str, object], ignored_schema)
        reason = ignored_schema_mapping.get("reason")
        fallback_reason = reason if isinstance(reason, str) else None
    elif isinstance(ignored_format, Mapping):
        ignored_format_mapping = cast(Mapping[str, object], ignored_format)
        reason = ignored_format_mapping.get("reason")
        fallback_reason = reason if isinstance(reason, str) else None
    return StructuredOutputDiagnosticsResponse(
        status=status_value,
        format=str(metadata["format"]),
        strategy=str(metadata["strategy"]),
        enforcement=str(metadata["enforcement"]),
        responseFormatMode=structured_output_response_format_mode(
            strategy=str(metadata["strategy"]),
        ),
        fallbackReason=fallback_reason,
        schemaSource=str(schema_source) if schema_source is not None else None,
        schema=cast(dict[str, object], schema) if isinstance(schema, dict) else None,
        ignoredSchema=cast(dict[str, object], ignored_schema)
        if isinstance(ignored_schema, dict)
        else None,
        ignoredFormat=cast(dict[str, object], ignored_format)
        if isinstance(ignored_format, dict)
        else None,
        citationBoundary=citation_boundary,
    )


def structured_output_response_format_mode(*, strategy: str) -> str:
    if strategy == "schema_passthrough":
        return "schema"
    if strategy == "json_object_schema":
        return "json_object"
    return "none"


def structured_output_citation_boundary(
    context_manifest: Mapping[str, object] | None,
) -> dict[str, object] | None:
    if not context_manifest_requires_citations(context_manifest):
        return None
    citation_ids = context_manifest_citation_ids(context_manifest)
    boundary: dict[str, object] = {
        "status": "enforced",
        "source": "context_manifest",
        "citationIds": citation_ids,
        "requiredMetadata": [
            "structured_output_allowed_citation_ids",
            "structured_output_citation_policy",
            "structured_output_citation_count",
        ],
    }
    if not citation_ids:
        boundary["reason"] = "missing_context_citation_ids"
    return boundary


def public_run_event_payload(payload: Mapping[str, Any]) -> dict[str, object]:
    sanitized = sanitize_public_metadata_value(payload)
    sanitized = redact_trace_payload(sanitized)
    if isinstance(sanitized, dict):
        public_payload = cast(dict[str, object], sanitized)
        reason = public_payload.pop("reason", None)
        if isinstance(reason, str) and reason.strip():
            public_payload["reasonPresent"] = True
        return public_payload
    return {}
