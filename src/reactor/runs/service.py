from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from inspect import isawaitable
from shlex import quote
from typing import Any, Protocol, cast

from jsonschema import SchemaError
from jsonschema.exceptions import UnknownType
from jsonschema.validators import Draft202012Validator
from langchain_core.messages import HumanMessage, ToolMessage

from reactor.agents.checkpoint_fork import (
    CheckpointForkError,
    latest_checkpoint_id,
    materialize_checkpoint_fork,
)
from reactor.agents.events import AgentStreamEvent
from reactor.agents.interrupts import ApprovalResumeDecision
from reactor.agents.langchain_agent import (
    LangChainInterruptAction,
    approval_required_tool_names,
    context_manifest_with_runtime_rag_citations,
    context_manifest_with_tool_output_guard,
    enforce_structured_response_boundary_with_metadata,
    extract_langchain_interrupt_actions,
    langchain_tool_output_guard,
    langchain_v2_stream_structured_response,
    langchain_v2_stream_tool_messages,
    planned_langchain_middleware_chain_metadata,
    stream_langchain_agent_events,
    tool_output_guard_error_code,
)
from reactor.agents.langchain_middleware import (
    LangChainMiddlewarePolicy,
    langchain_middleware_policy_from_mapping,
    langchain_middleware_policy_metadata,
)
from reactor.agents.runner import (
    RunResult,
    extract_native_langgraph_interrupt_actions,
    guard_block_result,
    latest_provider_usage,
    metadata_from_graph_result,
    native_langgraph_interrupts,
    public_run_metadata,
    response_policy_terminal_status,
    run_once,
    tool_state_specs,
)
from reactor.agents.runtime_config import (
    LANGGRAPH_NATIVE_CONFIG_METADATA,
    LANGGRAPH_NATIVE_RESUME_RUN_NAME,
    LANGGRAPH_NATIVE_RUN_TAGS,
    LANGGRAPH_NATIVE_STREAM_RUN_NAME,
    initial_reactor_state,
    langgraph_durable_config,
)
from reactor.agents.stores import GraphStore
from reactor.agents.streaming import (
    LANGCHAIN_RAW_STREAM_EVENTS_VERSION,
    langchain_v2_stream_event_to_agent_event,
    langchain_v2_stream_interrupt_lineage_invalid,
    langchain_v2_stream_interrupt_payload_invalid,
    langchain_v2_stream_interrupts,
    langgraph_stream_event_to_agent_event,
)
from reactor.core.runtime_settings import runtime_setting_value
from reactor.core.settings import Settings, database_required_for_runtime
from reactor.guards.input import InputGuardBlocked
from reactor.guards.output import OutputGuardBlocked
from reactor.kernel.ids import new_id
from reactor.observability.metrics import record_model_usage_metrics
from reactor.observability.tracing import trace_reactor_span
from reactor.observability.usage_ledger import UsageLedgerRecord
from reactor.persistence.approval_store import ApprovalRecord
from reactor.persistence.run_store import (
    RunCompletionEvent,
    RunEventRecord,
    RunStore,
    SessionRunRecord,
)
from reactor.providers.usage import TokenUsage, estimated_usage, usage_from_provider_metadata
from reactor.response.filters import (
    ResponseFilterChain,
    ResponseFilterContext,
    default_response_filter_chain,
)
from reactor.response.structured import ResponseFormat
from reactor.runs.lifecycle import RunLifecyclePublisher, publish_run_lifecycle_event
from reactor.runtime_settings.service import (
    GLOBAL_TENANT_ID,
    RuntimeSettingRecord,
    RuntimeSettingsResolver,
)
from reactor.tools.approval import ApprovalRequest
from reactor.tools.catalog import RISK_LEVELS, ToolSpec
from reactor.tools.execution import ToolHandler

ALLOWED_AGENT_RUNTIMES = {"langgraph", "langchain_agent"}
ALLOWED_STREAMING_AGENT_RUNTIMES = {"langgraph", "langchain_agent"}
CHECKPOINT_PROVENANCE_METADATA_KEYS = frozenset(
    {
        "checkpointId",
        "checkpoint_id",
        "source",
        "forkedFromRunId",
        "forkedFromThreadId",
        "forkedFromCheckpointNs",
        "forkedFromCheckpointId",
        "forkTargetThreadId",
        "forkTargetCheckpointNs",
        "forkedFromExecutionContract",
    }
)
LANGCHAIN_MIDDLEWARE_POLICY_SETTING_KEY = "langchain.middleware_policy"
TOOL_PROFILE_BUDGET_SETTING_KEY = "tools.profile_budget"
TOOL_PROFILE_BUDGET_FIELDS = frozenset(
    {
        "maxTools",
        "allowedRiskLevels",
        "allowedTools",
        "deniedTools",
    }
)
RESEARCH_FORCED_TOOL = "Rag:hybrid_search"
logger = logging.getLogger(__name__)


class ToolSpecProvider(Protocol):
    async def list_enabled_tool_specs(self, tenant_id: str) -> Sequence[ToolSpec]: ...


class RuntimeSettingsStore(Protocol):
    async def list(self, *, tenant_id: str | None = None) -> Sequence[RuntimeSettingRecord]: ...


class ApprovalRequestStore(Protocol):
    async def request_approval(self, request: ApprovalRequest) -> str: ...

    async def find_approval(
        self,
        *,
        tenant_id: str,
        approval_id: str,
    ) -> ApprovalRecord | None: ...


class ResearchStreamRejected(Exception):
    pass


class CheckpointForkStreamRejected(Exception):
    pass


class InterruptStreamConflict(Exception):
    pass


class InterruptStreamLineageInvalid(Exception):
    pass


class InterruptStreamPayloadInvalid(Exception):
    pass


class InterruptStreamActionInvalid(Exception):
    pass


class StructuredResponseStreamConflict(Exception):
    pass


class NativeGraphResultStreamConflict(Exception):
    pass


class RunCancellationConflict(Exception):
    pass


@dataclass(frozen=True)
class ToolProfileBudget:
    max_tools: int | None = None
    allowed_risk_levels: frozenset[str] | None = None
    allowed_tools: frozenset[str] | None = None
    denied_tools: frozenset[str] = frozenset()

    def validate(self) -> None:
        if self.max_tools is not None and self.max_tools < 0:
            raise ValueError("max_tools must be non-negative")
        if self.allowed_risk_levels is not None:
            invalid_risks = self.allowed_risk_levels - RISK_LEVELS
            if invalid_risks:
                raise ValueError(f"invalid risk levels: {sorted(invalid_risks)}")


@dataclass(frozen=True)
class ResolvedToolProfileBudget:
    budget: ToolProfileBudget
    source: str
    setting_key: str | None = None
    tenant_id: str | None = None

    def metadata(
        self,
        *,
        configured_tool_count: int,
        active_tool_count: int,
        active_tools: Sequence[str] = (),
        dropped_tools: Sequence[Mapping[str, object]] = (),
    ) -> dict[str, object]:
        if configured_tool_count < 0:
            raise ValueError("configured_tool_count must be non-negative")
        if active_tool_count < 0:
            raise ValueError("active_tool_count must be non-negative")
        if active_tool_count > configured_tool_count:
            raise ValueError("active_tool_count cannot exceed configured_tool_count")
        active_tool_names = list(active_tools)
        if len(active_tool_names) != active_tool_count:
            raise ValueError("active_tools length must match active_tool_count")
        dropped_tool_metadata = [dict(tool) for tool in dropped_tools]
        if active_tool_count + len(dropped_tool_metadata) != configured_tool_count:
            raise ValueError("active and dropped tool counts must match configured")
        metadata: dict[str, object] = {
            "source": self.source,
            "budget": tool_profile_budget_metadata(self.budget),
            "configuredToolCount": configured_tool_count,
            "activeToolCount": active_tool_count,
            "activeTools": active_tool_names,
            "droppedToolCount": len(dropped_tool_metadata),
            "droppedTools": dropped_tool_metadata,
        }
        if self.setting_key is not None:
            metadata["settingKey"] = self.setting_key
        if self.tenant_id is not None:
            metadata["tenantId"] = self.tenant_id
        return metadata


@dataclass(frozen=True)
class IgnoredToolProfileBudget:
    reason: str
    source: str
    setting_key: str | None = None
    tenant_id: str | None = None

    def metadata(self) -> dict[str, object]:
        metadata: dict[str, object] = {
            "status": "ignored",
            "reason": self.reason,
            "source": self.source,
        }
        if self.setting_key is not None:
            metadata["settingKey"] = self.setting_key
        if self.tenant_id is not None:
            metadata["tenantId"] = self.tenant_id
        return metadata


ToolProfileBudgetResolution = ResolvedToolProfileBudget | IgnoredToolProfileBudget


@dataclass(frozen=True)
class ToolExposure:
    tools: list[ToolSpec] | None
    resolved_budget: ToolProfileBudgetResolution | None = None
    configured_tool_count: int = 0
    active_tool_count: int = 0
    active_tools: tuple[str, ...] = ()
    dropped_tools: tuple[Mapping[str, object], ...] = ()

    def resolved_budget_metadata(self) -> dict[str, object] | None:
        if self.resolved_budget is None:
            return None
        if isinstance(self.resolved_budget, IgnoredToolProfileBudget):
            return self.resolved_budget.metadata()
        return self.resolved_budget.metadata(
            configured_tool_count=self.configured_tool_count,
            active_tool_count=self.active_tool_count,
            active_tools=self.active_tools,
            dropped_tools=self.dropped_tools,
        )


@dataclass(frozen=True)
class ToolProfileBudgetApplication:
    tools: list[ToolSpec]
    dropped_tools: tuple[Mapping[str, object], ...] = ()


@dataclass(frozen=True)
class CheckpointReplayResolution:
    checkpoint_id: str | None = None
    metadata: dict[str, object] | None = None
    blocked: bool = False


@dataclass(frozen=True)
class TrustedCheckpointFork:
    source_run_id: str
    source_thread_id: str
    source_checkpoint_ns: str
    source_checkpoint_id: str | None
    source_runtime: str
    source_graph_profile: str | None
    target_thread_id: str
    target_checkpoint_ns: str

    def metadata(self) -> dict[str, object]:
        metadata: dict[str, object] = {
            "source": "checkpoint_fork",
            "forkedFromRunId": self.source_run_id,
            "forkedFromThreadId": self.source_thread_id,
            "forkedFromCheckpointNs": self.source_checkpoint_ns,
            "forkTargetThreadId": self.target_thread_id,
            "forkTargetCheckpointNs": self.target_checkpoint_ns,
            "forkedFromExecutionContract": {
                "runtime": self.source_runtime,
                "graphProfile": self.source_graph_profile,
            },
        }
        if self.source_checkpoint_id is not None:
            metadata["forkedFromCheckpointId"] = self.source_checkpoint_id
        return metadata


@dataclass(frozen=True)
class ResolvedLangChainMiddlewarePolicy:
    policy: LangChainMiddlewarePolicy
    source: str
    setting_key: str | None = None
    tenant_id: str | None = None

    def metadata(self) -> dict[str, object]:
        metadata: dict[str, object] = {
            "status": "applied",
            "source": self.source,
            "policy": langchain_middleware_policy_metadata(self.policy),
        }
        if self.setting_key is not None:
            metadata["settingKey"] = self.setting_key
        if self.tenant_id is not None:
            metadata["tenantId"] = self.tenant_id
        return metadata


@dataclass(frozen=True)
class IgnoredLangChainMiddlewarePolicy:
    reason: str
    source: str
    setting_key: str | None = None
    tenant_id: str | None = None

    def metadata(self) -> dict[str, object]:
        metadata: dict[str, object] = {
            "status": "ignored",
            "reason": self.reason,
            "source": self.source,
        }
        if self.setting_key is not None:
            metadata["settingKey"] = self.setting_key
        if self.tenant_id is not None:
            metadata["tenantId"] = self.tenant_id
        return metadata


LangChainMiddlewarePolicyResolution = (
    ResolvedLangChainMiddlewarePolicy | IgnoredLangChainMiddlewarePolicy
)


@dataclass(frozen=True)
class ResolvedStructuredOutput:
    response_format: str | None
    schema: dict[str, object] | None
    schema_source: str | None
    ignored_schema: dict[str, object] | None = None
    ignored_format: dict[str, object] | None = None

    @property
    def strategy(self) -> str:
        if self.schema is not None:
            return "schema_passthrough"
        if (self.response_format or "").upper() == "JSON":
            return "json_object_schema"
        return "reactor_boundary"

    @property
    def effective_format(self) -> str:
        if self.schema is not None:
            return ResponseFormat.JSON.value
        return self.response_format or ResponseFormat.TEXT.value

    def metadata(self) -> dict[str, object] | None:
        if (
            self.response_format is None
            and self.schema is None
            and self.ignored_schema is None
            and self.ignored_format is None
        ):
            return None
        metadata: dict[str, object] = {
            "format": self.effective_format,
            "strategy": self.strategy,
            "enforcement": "langchain_response_format_and_reactor_boundary",
        }
        if self.schema_source is not None:
            metadata["schemaSource"] = self.schema_source
        if self.schema is not None:
            metadata["schema"] = self.schema
        if self.ignored_schema is not None:
            metadata["ignoredSchema"] = self.ignored_schema
        if self.ignored_format is not None:
            metadata["ignoredFormat"] = self.ignored_format
        return metadata


@dataclass(frozen=True)
class RunPreflightResult:
    status: str
    tenant_id: str
    user_id: str
    thread_id: str
    checkpoint_ns: str
    runtime: str
    provider: str
    model: str
    metadata: dict[str, Any]
    structured_output: ResolvedStructuredOutput
    tool_exposure: ToolExposure
    middleware_policy: LangChainMiddlewarePolicyResolution | None
    checkpoint_replay: CheckpointReplayResolution


def unresumable_interrupt_result(
    result: RunResult,
    *,
    reason: str,
) -> RunResult:
    return replace(
        result,
        status="failed",
        response="Agent approval request could not be persisted safely.",
        response_metadata={
            **result.response_metadata,
            "approval_status": "unavailable",
            "stop_reason": reason,
        },
        interrupt_actions=(),
    )


def missing_checkpoint_provenance_result(result: RunResult) -> RunResult:
    return replace(
        result,
        status="failed",
        response="Run checkpoint provenance could not be persisted safely.",
        response_metadata={
            **result.response_metadata,
            "stop_reason": "checkpoint_provenance_unavailable",
        },
        interrupt_actions=(),
    )


def concurrent_cancellation_result(result: RunResult) -> RunResult:
    return replace(
        result,
        status="cancelled",
        response="Run cancelled.",
        token_usage=None,
        response_metadata={"stop_reason": "concurrent_cancellation"},
        interrupt_actions=(),
    )


def resume_failure_result(
    *,
    run_id: str,
    tenant_id: str,
    user_id: str,
    thread_id: str,
    checkpoint_ns: str,
    provider: str,
    model: str,
    reason: str,
) -> RunResult:
    return RunResult(
        run_id=run_id,
        tenant_id=tenant_id,
        user_id=user_id,
        thread_id=thread_id,
        checkpoint_ns=checkpoint_ns,
        status="failed",
        response="Agent approval could not resume the interrupted run safely.",
        provider=provider,
        model=model,
        response_metadata={
            "approval_status": "invalid",
            "stop_reason": reason,
        },
    )


def approval_resume_provenance_matches(
    approval: ApprovalRecord,
    *,
    runtime: str,
    thread_id: str,
    checkpoint_ns: str,
) -> bool:
    payload = approval.request_payload
    return (
        payload.get("runtime") == runtime
        and payload.get("thread_id") == thread_id
        and payload.get("checkpoint_ns") == checkpoint_ns
    )


def approval_tool_matches_current_exposure(
    approval: ApprovalRecord,
    tools: Sequence[ToolSpec] | None,
) -> bool:
    tool_name = approval.request_payload.get("tool_name")
    if not isinstance(tool_name, str) or not tool_name.strip():
        return False
    matches = [
        tool
        for tool in tools or ()
        if tool.enabled
        and tool.approval_required
        and tool.catalog_id == approval.tool_id
        and tool.qualified_name == tool_name
    ]
    return len(matches) == 1


class RunService:
    def __init__(
        self,
        settings: Settings,
        run_store: RunStore | None,
        graph: Any | None = None,
        usage_ledger: Any | None = None,
        tool_provider: ToolSpecProvider | None = None,
        tool_handler: ToolHandler | None = None,
        tool_invocation_store: Any | None = None,
        builtin_tool_specs: Callable[[str], Sequence[ToolSpec]] | None = None,
        checkpointer: object | None = None,
        graph_store: GraphStore | None = None,
        response_filter_chain: ResponseFilterChain | None = None,
        run_lifecycle_publisher: RunLifecyclePublisher | None = None,
        runtime_settings_store: RuntimeSettingsStore | None = None,
        approval_store: ApprovalRequestStore | None = None,
    ) -> None:
        self._settings = settings
        self._run_store = run_store
        self._graph = graph
        self._usage_ledger = usage_ledger
        self._tool_provider = tool_provider
        self._tool_handler = tool_handler
        self._tool_invocation_store = tool_invocation_store
        self._builtin_tool_specs = builtin_tool_specs
        self._checkpointer = checkpointer
        self._graph_store = graph_store
        self._response_filter_chain = response_filter_chain or default_response_filter_chain()
        self._run_lifecycle_publisher = run_lifecycle_publisher
        self._runtime_settings_store = runtime_settings_store
        self._approval_store = approval_store

    async def preflight_run(
        self,
        message: str,
        *,
        tenant_id: str = "local",
        user_id: str = "anonymous",
        thread_id: str | None = None,
        checkpoint_ns: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RunPreflightResult:
        actual_thread_id = thread_id or self._settings.default_thread_id
        actual_checkpoint_ns = checkpoint_ns or self._settings.default_checkpoint_ns
        run_metadata = run_metadata_with_defaults(
            metadata,
            checkpoint_ns=actual_checkpoint_ns,
        )
        runtime = str(run_metadata.get("runtime") or "langgraph")
        provider = str(run_metadata.get("modelProvider") or self._settings.default_model_provider)
        model = str(run_metadata.get("model") or self._settings.default_model)
        structured_output = resolved_structured_output(run_metadata)
        checkpoint_replay = checkpoint_replay_resolution(
            None,
            target_thread_id=actual_thread_id,
            target_checkpoint_ns=actual_checkpoint_ns,
        )
        runtime_settings_resolver = (
            await self._runtime_settings_resolver(tenant_id=tenant_id)
            if runtime == "langchain_agent"
            and "toolProfileBudget" not in run_metadata
            and "middlewarePolicy" not in run_metadata
            else None
        )
        tool_exposure = (
            await self._enabled_tools_for_runtime(
                runtime,
                tenant_id=tenant_id,
                metadata=run_metadata,
                runtime_settings_resolver=runtime_settings_resolver,
            )
            if runtime in ALLOWED_AGENT_RUNTIMES
            else ToolExposure(tools=None)
        )
        middleware_policy: LangChainMiddlewarePolicyResolution | None = None
        if runtime == "langchain_agent":
            middleware_policy = await self._resolved_langchain_middleware_policy(
                run_metadata,
                tenant_id=tenant_id,
                runtime_settings_resolver=runtime_settings_resolver,
            )
        return RunPreflightResult(
            status="ready" if runtime in ALLOWED_AGENT_RUNTIMES else "rejected",
            tenant_id=tenant_id,
            user_id=user_id,
            thread_id=actual_thread_id,
            checkpoint_ns=actual_checkpoint_ns,
            runtime=runtime,
            provider=provider,
            model=model,
            metadata=run_metadata,
            structured_output=structured_output,
            tool_exposure=tool_exposure,
            middleware_policy=middleware_policy,
            checkpoint_replay=checkpoint_replay,
        )

    async def create_run(
        self,
        message: str,
        *,
        tenant_id: str = "local",
        user_id: str = "anonymous",
        trusted_user_groups: tuple[str, ...] = (),
        thread_id: str | None = None,
        checkpoint_ns: str | None = None,
        metadata: dict[str, Any] | None = None,
        checkpoint_fork: TrustedCheckpointFork | None = None,
    ) -> RunResult:
        run_id = new_id("run")
        actual_thread_id = thread_id or self._settings.default_thread_id
        actual_checkpoint_ns = checkpoint_ns or self._settings.default_checkpoint_ns
        run_metadata = run_metadata_with_defaults(
            metadata,
            checkpoint_ns=actual_checkpoint_ns,
            checkpoint_fork=checkpoint_fork,
        )
        provider = str(run_metadata.get("modelProvider") or self._settings.default_model_provider)
        model = str(run_metadata.get("model") or self._settings.default_model)
        with trace_reactor_span(
            "reactor.run",
            {
                "reactor.run_id": run_id,
                "reactor.tenant_id": tenant_id,
                "reactor.user_id": user_id,
                "reactor.thread_id": actual_thread_id,
                "reactor.checkpoint_ns": actual_checkpoint_ns,
                "reactor.model.provider": provider,
                "reactor.model.name": model,
            },
        ) as span:
            if self._run_store is not None:
                try:
                    await self._run_store.record_started(
                        run_id=run_id,
                        tenant_id=tenant_id,
                        user_id=user_id,
                        thread_id=actual_thread_id,
                        checkpoint_ns=actual_checkpoint_ns,
                        input_text=message,
                        metadata=run_metadata,
                    )
                except asyncio.CancelledError:
                    await self._persist_external_run_cancellation(
                        run_id=run_id,
                        tenant_id=tenant_id,
                        user_id=user_id,
                        thread_id=actual_thread_id,
                        checkpoint_ns=actual_checkpoint_ns,
                        provider=provider,
                        model=model,
                        run_metadata=run_metadata,
                    )
                    raise
            runtime = str(run_metadata.get("runtime") or "langgraph")
            if runtime not in ALLOWED_AGENT_RUNTIMES:
                result = RunResult(
                    run_id=run_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    thread_id=actual_thread_id,
                    checkpoint_ns=actual_checkpoint_ns,
                    status="rejected",
                    response="Unsupported agent runtime.",
                    provider=provider,
                    model=model,
                )
                result = await self._filter_invoke_result_response(
                    result,
                    tools_used=[],
                    run_metadata=run_metadata,
                )
                if self._run_store is not None:
                    completion_transitioned = await self._record_invoke_completion(
                        result=result,
                        metadata={
                            **run_metadata,
                            "checkpoint_ns": result.checkpoint_ns,
                            "rejection_reason": "unsupported_runtime",
                        },
                        run_metadata=run_metadata,
                    )
                    if completion_transitioned is False:
                        result = concurrent_cancellation_result(result)
                span.set_attribute("reactor.status", result.status)
                return result
            runtime_settings_resolver: RuntimeSettingsResolver | None = None
            try:
                if runtime == "langchain_agent" and (
                    "toolProfileBudget" not in run_metadata
                    and "middlewarePolicy" not in run_metadata
                ):
                    runtime_settings_resolver = await self._runtime_settings_resolver(
                        tenant_id=tenant_id
                    )
                tool_exposure = await self._enabled_tools_for_runtime(
                    runtime,
                    tenant_id=tenant_id,
                    metadata=run_metadata,
                    runtime_settings_resolver=runtime_settings_resolver,
                )
            except asyncio.CancelledError:
                await self._persist_external_run_cancellation(
                    run_id=run_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    thread_id=actual_thread_id,
                    checkpoint_ns=actual_checkpoint_ns,
                    provider=provider,
                    model=model,
                    run_metadata=run_metadata,
                )
                raise
            tools = tool_exposure.tools
            research_block_plan = blocked_research_plan_from_tool_exposure(
                run_metadata,
                tool_exposure,
                message=message,
            )
            if research_block_plan is not None:
                result = RunResult(
                    run_id=run_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    thread_id=actual_thread_id,
                    checkpoint_ns=actual_checkpoint_ns,
                    status="rejected",
                    response=(
                        "Research profile requires Rag:hybrid_search, but that tool is not active."
                    ),
                    provider=provider,
                    model=model,
                    response_metadata={
                        "stop_reason": "forced_tool_unavailable",
                        "research_plan": research_block_plan,
                    },
                )
                result = await self._filter_invoke_result_response(
                    result,
                    tools_used=[],
                    run_metadata=run_metadata,
                )
                if self._run_store is not None:
                    completed_metadata = {
                        **run_metadata,
                        "checkpoint_ns": result.checkpoint_ns,
                        "rejection_reason": "forced_tool_unavailable",
                    }
                    completed_metadata.update(public_run_metadata(result.response_metadata))
                    resolved_tool_profile_budget_metadata = tool_exposure.resolved_budget_metadata()
                    if resolved_tool_profile_budget_metadata is not None:
                        completed_metadata["resolvedToolProfileBudget"] = (
                            resolved_tool_profile_budget_metadata
                        )
                    completion_transitioned = await self._record_invoke_completion(
                        result=result,
                        metadata=completed_metadata,
                        run_metadata=run_metadata,
                    )
                    if completion_transitioned is False:
                        result = concurrent_cancellation_result(result)
                span.set_attribute("reactor.status", result.status)
                return result
            structured_output = resolved_structured_output(run_metadata)
            checkpoint_replay = checkpoint_replay_resolution(
                checkpoint_fork,
                target_thread_id=actual_thread_id,
                target_checkpoint_ns=actual_checkpoint_ns,
            )
            try:
                checkpoint_replay = await materialize_checkpoint_replay(
                    self._checkpointer,
                    tenant_id=tenant_id,
                    checkpoint_fork=checkpoint_fork,
                    target_runtime=runtime,
                    target_graph_profile=optional_metadata_string(run_metadata.get("graphProfile")),
                    resolution=checkpoint_replay,
                    target_thread_id=actual_thread_id,
                    target_checkpoint_ns=actual_checkpoint_ns,
                )
            except asyncio.CancelledError:
                await self._persist_external_run_cancellation(
                    run_id=run_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    thread_id=actual_thread_id,
                    checkpoint_ns=actual_checkpoint_ns,
                    provider=provider,
                    model=model,
                    run_metadata=run_metadata,
                )
                raise
            if checkpoint_replay.blocked:
                result = RunResult(
                    run_id=run_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    thread_id=actual_thread_id,
                    checkpoint_ns=actual_checkpoint_ns,
                    status="failed",
                    response="Checkpoint fork could not be prepared safely.",
                    provider=provider,
                    model=model,
                    response_metadata={"stop_reason": "checkpoint_fork_failed"},
                )
                result = await self._filter_invoke_result_response(
                    result,
                    tools_used=[],
                    run_metadata=run_metadata,
                )
                if self._run_store is not None:
                    completion_transitioned = await self._record_invoke_completion(
                        result=result,
                        metadata={
                            **run_metadata,
                            "checkpoint_ns": result.checkpoint_ns,
                            "checkpointReplay": checkpoint_replay.metadata or {},
                        },
                        run_metadata=run_metadata,
                    )
                    if completion_transitioned is False:
                        result = concurrent_cancellation_result(result)
                span.set_attribute("reactor.status", result.status)
                return result
            resolved_middleware_policy: LangChainMiddlewarePolicyResolution | None = None
            if runtime == "langchain_agent":
                try:
                    resolved_middleware_policy = await self._resolved_langchain_middleware_policy(
                        run_metadata,
                        tenant_id=tenant_id,
                        runtime_settings_resolver=runtime_settings_resolver,
                    )
                except asyncio.CancelledError:
                    await self._persist_external_run_cancellation(
                        run_id=run_id,
                        tenant_id=tenant_id,
                        user_id=user_id,
                        thread_id=actual_thread_id,
                        checkpoint_ns=actual_checkpoint_ns,
                        provider=provider,
                        model=model,
                        run_metadata=run_metadata,
                    )
                    raise
            middleware_policy = (
                resolved_middleware_policy.policy
                if isinstance(resolved_middleware_policy, ResolvedLangChainMiddlewarePolicy)
                else None
            )
            try:
                result = await run_once(
                    message,
                    self._settings,
                    run_id=run_id,
                    graph=self._graph,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    trusted_user_groups=trusted_user_groups,
                    thread_id=actual_thread_id,
                    checkpoint_ns=actual_checkpoint_ns,
                    checkpoint_id=checkpoint_replay.checkpoint_id,
                    provider=provider,
                    model=model,
                    system_prompt=optional_metadata_string(run_metadata.get("systemPrompt")),
                    response_format=structured_output.response_format,
                    structured_output_schema=structured_output.schema,
                    fallback_models=optional_metadata_string_list(
                        run_metadata.get("fallbackModels")
                    ),
                    middleware_policy=middleware_policy,
                    graph_profile=optional_metadata_string(run_metadata.get("graphProfile")),
                    runtime=runtime,
                    tools=tools,
                    tool_handler=self._tool_handler,
                    tool_invocation_store=self._tool_invocation_store,
                    checkpointer=self._checkpointer,
                    graph_store=self._graph_store,
                    integration_context=integration_context_from_metadata(run_metadata),
                    context_manifest=optional_metadata_json_object(
                        run_metadata.get("contextManifest")
                    ),
                )
            except asyncio.CancelledError:
                await self._persist_external_run_cancellation(
                    run_id=run_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    thread_id=actual_thread_id,
                    checkpoint_ns=actual_checkpoint_ns,
                    provider=provider,
                    model=model,
                    run_metadata=run_metadata,
                )
                raise
            try:
                last_checkpoint_id = (
                    await latest_checkpoint_id(
                        self._checkpointer,
                        config=langgraph_durable_config(
                            tenant_id=tenant_id,
                            thread_id=actual_thread_id,
                            checkpoint_ns=actual_checkpoint_ns,
                        ),
                    )
                    if result.status in {"completed", "interrupted"} and self._run_store is not None
                    else None
                )
            except asyncio.CancelledError:
                await self._persist_external_run_cancellation(
                    run_id=run_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    thread_id=actual_thread_id,
                    checkpoint_ns=actual_checkpoint_ns,
                    provider=provider,
                    model=model,
                    run_metadata=run_metadata,
                )
                raise
            if (
                result.status == "completed"
                and database_required_for_runtime(self._settings)
                and last_checkpoint_id is None
            ):
                result = missing_checkpoint_provenance_result(result)
            elif result.status == "interrupted" and last_checkpoint_id is None:
                result = unresumable_interrupt_result(
                    result,
                    reason="checkpoint_provenance_unavailable",
                )
            elif result.status == "interrupted":
                try:
                    result = await self._persist_interrupt_approval(
                        result,
                        tools=tools,
                        runtime=runtime,
                    )
                except asyncio.CancelledError:
                    await self._persist_external_run_cancellation(
                        run_id=run_id,
                        tenant_id=tenant_id,
                        user_id=user_id,
                        thread_id=actual_thread_id,
                        checkpoint_ns=actual_checkpoint_ns,
                        provider=provider,
                        model=model,
                        run_metadata=run_metadata,
                    )
                    raise
            result = await self._filter_invoke_result_response(
                result,
                tools_used=[tool.qualified_name for tool in tools or []],
                run_metadata=run_metadata,
            )
            if self._run_store is not None:
                completed_metadata = {**run_metadata, "checkpoint_ns": result.checkpoint_ns}
                completed_metadata.update(public_run_metadata(result.response_metadata))
                if last_checkpoint_id is not None:
                    completed_metadata["last_checkpoint_id"] = last_checkpoint_id
                token_usage = token_usage_metadata(result.token_usage)
                if token_usage is not None:
                    completed_metadata["tokenUsage"] = token_usage
                if checkpoint_replay.metadata is not None:
                    completed_metadata["checkpointReplay"] = checkpoint_replay.metadata
                if resolved_middleware_policy is not None:
                    completed_metadata["langchainMiddlewarePolicy"] = (
                        resolved_middleware_policy.metadata()
                    )
                structured_output_metadata = structured_output.metadata()
                if structured_output_metadata is not None:
                    completed_metadata["structuredOutput"] = structured_output_metadata
                resolved_tool_profile_budget_metadata = tool_exposure.resolved_budget_metadata()
                if resolved_tool_profile_budget_metadata is not None:
                    completed_metadata["resolvedToolProfileBudget"] = (
                        resolved_tool_profile_budget_metadata
                    )
                guard_block_metadata = result.response_metadata.get("guardBlock")
                if isinstance(guard_block_metadata, Mapping):
                    completed_metadata["guardBlock"] = dict(
                        cast(Mapping[str, object], guard_block_metadata)
                    )
                completion_transitioned = await self._record_invoke_completion(
                    result=result,
                    metadata=completed_metadata,
                    run_metadata=run_metadata,
                )
                if completion_transitioned is False:
                    result = concurrent_cancellation_result(result)
            await self._record_usage(result)
            span.set_attribute("reactor.status", result.status)
            if result.token_usage is not None:
                span.set_attribute("reactor.tokens.input", result.token_usage.input_tokens)
                span.set_attribute("reactor.tokens.output", result.token_usage.output_tokens)
                span.set_attribute("reactor.tokens.total", result.token_usage.total_tokens)
                span.set_attribute("reactor.tokens.cached", result.token_usage.cached_tokens)
                span.set_attribute("reactor.tokens.reasoning", result.token_usage.reasoning_tokens)
            return result

    async def _persist_interrupt_approval(
        self,
        result: RunResult,
        *,
        tools: Sequence[ToolSpec] | None,
        runtime: str,
    ) -> RunResult:
        if self._approval_store is None:
            return unresumable_interrupt_result(
                result,
                reason="approval_persistence_unavailable",
            )
        if len(result.interrupt_actions) != 1:
            return unresumable_interrupt_result(
                result,
                reason="unsupported_interrupt_action_batch",
            )
        action = result.interrupt_actions[0]
        matches = [
            tool
            for tool in tools or ()
            if tool.enabled
            and tool.approval_required
            and tool.qualified_name == action.tool_name
            and tool.catalog_id is not None
        ]
        if len(matches) != 1:
            return unresumable_interrupt_result(
                result,
                reason="interrupt_tool_not_durable",
            )
        tool = matches[0]
        tool_id = cast(str, tool.catalog_id)
        request_payload = {
            "runtime": runtime,
            "thread_id": result.thread_id,
            "checkpoint_ns": result.checkpoint_ns,
            "decision_index": 0,
            "decision_count": 1,
            "tool_name": action.tool_name,
            "tool_input": dict(action.arguments),
        }
        try:
            approval_id = await self._approval_store.request_approval(
                ApprovalRequest(
                    tenant_id=result.tenant_id,
                    run_id=result.run_id,
                    tool_id=tool_id,
                    requested_by=result.user_id,
                    request_payload=request_payload,
                )
            )
        except Exception:
            return unresumable_interrupt_result(
                result,
                reason="approval_persistence_failed",
            )
        approval_id = approval_id.strip()
        if not approval_id:
            return unresumable_interrupt_result(
                result,
                reason="approval_persistence_invalid_id",
            )
        approval_request = {
            "run_id": result.run_id,
            "tenant_id": result.tenant_id,
            "tool_id": tool_id,
            "requested_by": result.user_id,
            "tool_risk_level": tool.risk_level,
            "tool_timeout_ms": tool.timeout_ms,
        }
        await publish_run_lifecycle_event(
            self._run_lifecycle_publisher,
            {
                "event_type": "approval.requested",
                "approval_id": approval_id,
                "tenant_id": result.tenant_id,
                "run_id": result.run_id,
                "tool_id": tool_id,
                "requested_by": result.user_id,
                "status": "pending",
            },
        )
        return replace(
            result,
            response_metadata={
                **result.response_metadata,
                "approval_id": approval_id,
                "approval_request": approval_request,
            },
        )

    async def _filter_result_response(
        self,
        result: RunResult,
        *,
        tools_used: list[str],
    ) -> RunResult:
        if self._response_filter_chain.size <= 0 or not result.response:
            return result
        filtered = await self._response_filter_chain.apply(
            result.response,
            ResponseFilterContext(
                tenant_id=result.tenant_id,
                user_id=result.user_id,
                tools_used=tools_used,
                duration_ms=0,
            ),
        )
        if filtered == result.response:
            return result
        return replace(result, response=filtered)

    async def _record_invoke_completion(
        self,
        *,
        result: RunResult,
        metadata: Mapping[str, Any],
        run_metadata: Mapping[str, Any],
        completion_events: Sequence[RunCompletionEvent] = (),
    ) -> bool | None:
        if self._run_store is None:
            return None
        try:
            if completion_events:
                return await self._run_store.record_completed(
                    result=result,
                    metadata=metadata,
                    completion_events=completion_events,
                )
            return await self._run_store.record_completed(
                result=result,
                metadata=metadata,
            )
        except asyncio.CancelledError:
            await self._persist_external_run_cancellation(
                run_id=result.run_id,
                tenant_id=result.tenant_id,
                user_id=result.user_id,
                thread_id=result.thread_id,
                checkpoint_ns=result.checkpoint_ns,
                provider=result.provider,
                model=result.model,
                run_metadata=run_metadata,
            )
            raise

    async def _filter_invoke_result_response(
        self,
        result: RunResult,
        *,
        tools_used: list[str],
        run_metadata: Mapping[str, Any],
    ) -> RunResult:
        try:
            return await self._filter_result_response(result, tools_used=tools_used)
        except asyncio.CancelledError:
            await self._persist_external_run_cancellation(
                run_id=result.run_id,
                tenant_id=result.tenant_id,
                user_id=result.user_id,
                thread_id=result.thread_id,
                checkpoint_ns=result.checkpoint_ns,
                provider=result.provider,
                model=result.model,
                run_metadata=run_metadata,
            )
            raise

    async def _filter_stream_event_payload(
        self,
        event: AgentStreamEvent,
        *,
        tenant_id: str,
        user_id: str,
    ) -> AgentStreamEvent:
        if self._response_filter_chain.size <= 0 or not event.payload:
            return event
        context = ResponseFilterContext(
            tenant_id=tenant_id,
            user_id=user_id,
            tools_used=[],
            duration_ms=0,
        )
        filtered_payload = await self._filter_stream_payload_value(event.payload, context)
        if filtered_payload is event.payload or not isinstance(filtered_payload, Mapping):
            return event
        return replace(event, payload=cast(Mapping[str, Any], filtered_payload))

    async def _filter_stream_payload_value(
        self,
        value: object,
        context: ResponseFilterContext,
    ) -> object:
        if isinstance(value, str):
            return await self._response_filter_chain.apply(value, context)
        if isinstance(value, Mapping):
            typed_value = cast(Mapping[object, object], value)
            return {
                key: await self._filter_stream_payload_value(nested, context)
                for key, nested in typed_value.items()
            }
        if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
            return [
                await self._filter_stream_payload_value(nested, context)
                for nested in cast(Sequence[object], value)
            ]
        return value

    async def _enabled_tools_for_runtime(
        self,
        runtime: str,
        *,
        tenant_id: str,
        metadata: Mapping[str, Any],
        approval_resume: bool = False,
        runtime_settings_resolver: RuntimeSettingsResolver | None = None,
    ) -> ToolExposure:
        if (
            runtime == "langgraph"
            and optional_metadata_string(metadata.get("graphProfile")) is None
            and not approval_resume
        ):
            return ToolExposure(tools=None)
        if runtime not in ALLOWED_AGENT_RUNTIMES:
            return ToolExposure(tools=None)
        tools = (
            list(await self._tool_provider.list_enabled_tool_specs(tenant_id))
            if self._tool_provider is not None
            else []
        )
        if self._builtin_tool_specs is not None:
            existing = {tool.qualified_name for tool in tools}
            tools.extend(
                tool
                for tool in self._builtin_tool_specs(tenant_id)
                if tool.enabled and tool.qualified_name not in existing
            )
        if not tools:
            return ToolExposure(tools=None)
        configured_tool_count = len(tools)
        resolved_budget = await self._resolved_tool_profile_budget(
            metadata,
            tenant_id=tenant_id,
            runtime_settings_resolver=runtime_settings_resolver,
        )
        dropped_tools: tuple[Mapping[str, object], ...] = ()
        if isinstance(resolved_budget, ResolvedToolProfileBudget):
            budget_application = apply_tool_profile_budget_with_evidence(
                tools,
                resolved_budget.budget,
            )
            tools = budget_application.tools
            dropped_tools = budget_application.dropped_tools
        return ToolExposure(
            tools=tools or None,
            resolved_budget=resolved_budget,
            configured_tool_count=configured_tool_count,
            active_tool_count=len(tools),
            active_tools=tuple(tool.qualified_name for tool in tools),
            dropped_tools=dropped_tools,
        )

    async def _tool_profile_budget(
        self,
        metadata: Mapping[str, Any],
        *,
        tenant_id: str,
    ) -> ToolProfileBudget | None:
        resolved = await self._resolved_tool_profile_budget(metadata, tenant_id=tenant_id)
        return resolved.budget if isinstance(resolved, ResolvedToolProfileBudget) else None

    async def _resolved_tool_profile_budget(
        self,
        metadata: Mapping[str, Any],
        *,
        tenant_id: str,
        runtime_settings_resolver: RuntimeSettingsResolver | None = None,
    ) -> ToolProfileBudgetResolution | None:
        if "toolProfileBudget" in metadata:
            metadata_budget = tool_profile_budget_from_mapping(metadata.get("toolProfileBudget"))
            if metadata_budget is None:
                return IgnoredToolProfileBudget(
                    reason="invalid_metadata_budget",
                    source="metadata",
                )
            return ResolvedToolProfileBudget(budget=metadata_budget, source="metadata")
        return await self._resolved_runtime_setting_tool_profile_budget(
            tenant_id=tenant_id,
            runtime_settings_resolver=runtime_settings_resolver,
        )

    async def _runtime_setting_tool_profile_budget(
        self,
        *,
        tenant_id: str,
    ) -> ToolProfileBudget | None:
        resolved = await self._resolved_runtime_setting_tool_profile_budget(tenant_id=tenant_id)
        return resolved.budget if isinstance(resolved, ResolvedToolProfileBudget) else None

    async def _resolved_runtime_setting_tool_profile_budget(
        self,
        *,
        tenant_id: str,
        runtime_settings_resolver: RuntimeSettingsResolver | None = None,
    ) -> ToolProfileBudgetResolution | None:
        resolver = runtime_settings_resolver
        if resolver is None:
            resolver = await self._runtime_settings_resolver(tenant_id=tenant_id)
        if resolver is None:
            return None
        record = resolver.find(TOOL_PROFILE_BUDGET_SETTING_KEY, tenant_id=tenant_id)
        if record is None:
            return None
        source = (
            "tenant_runtime_setting" if record.tenant_id == tenant_id else "global_runtime_setting"
        )
        try:
            value = runtime_setting_value(record)
        except ValueError:
            return IgnoredToolProfileBudget(
                reason="invalid_runtime_setting",
                source=source,
                setting_key=TOOL_PROFILE_BUDGET_SETTING_KEY,
                tenant_id=record.tenant_id,
            )
        budget = tool_profile_budget_from_mapping(value)
        if budget is None:
            return IgnoredToolProfileBudget(
                reason="invalid_runtime_setting",
                source=source,
                setting_key=TOOL_PROFILE_BUDGET_SETTING_KEY,
                tenant_id=record.tenant_id,
            )
        return ResolvedToolProfileBudget(
            budget=budget,
            source=source,
            setting_key=TOOL_PROFILE_BUDGET_SETTING_KEY,
            tenant_id=record.tenant_id,
        )

    async def _resolved_langchain_middleware_policy(
        self,
        metadata: Mapping[str, Any],
        *,
        tenant_id: str,
        runtime_settings_resolver: RuntimeSettingsResolver | None = None,
    ) -> LangChainMiddlewarePolicyResolution | None:
        if "middlewarePolicy" in metadata:
            metadata_policy = optional_metadata_middleware_policy(metadata.get("middlewarePolicy"))
            if metadata_policy is None:
                return IgnoredLangChainMiddlewarePolicy(
                    reason="invalid_metadata_policy",
                    source="metadata",
                )
            return ResolvedLangChainMiddlewarePolicy(
                policy=metadata_policy,
                source="metadata",
            )
        return await self._resolved_runtime_setting_middleware_policy(
            tenant_id=tenant_id,
            runtime_settings_resolver=runtime_settings_resolver,
        )

    async def _langchain_middleware_policy(
        self,
        metadata: Mapping[str, Any],
        *,
        tenant_id: str,
    ) -> LangChainMiddlewarePolicy | None:
        resolved = await self._resolved_langchain_middleware_policy(metadata, tenant_id=tenant_id)
        if not isinstance(resolved, ResolvedLangChainMiddlewarePolicy):
            return None
        return resolved.policy

    async def _resolved_runtime_setting_middleware_policy(
        self,
        *,
        tenant_id: str,
        runtime_settings_resolver: RuntimeSettingsResolver | None = None,
    ) -> LangChainMiddlewarePolicyResolution | None:
        resolver = runtime_settings_resolver
        if resolver is None:
            resolver = await self._runtime_settings_resolver(tenant_id=tenant_id)
        if resolver is None:
            return None
        record = resolver.find(LANGCHAIN_MIDDLEWARE_POLICY_SETTING_KEY, tenant_id=tenant_id)
        if record is None:
            return None
        source = (
            "tenant_runtime_setting" if record.tenant_id == tenant_id else "global_runtime_setting"
        )
        try:
            value = runtime_setting_value(record)
        except ValueError:
            return IgnoredLangChainMiddlewarePolicy(
                reason="invalid_runtime_setting",
                source=source,
                setting_key=LANGCHAIN_MIDDLEWARE_POLICY_SETTING_KEY,
                tenant_id=record.tenant_id,
            )
        policy = optional_metadata_middleware_policy(value)
        if policy is None:
            return IgnoredLangChainMiddlewarePolicy(
                reason="invalid_runtime_setting",
                source=source,
                setting_key=LANGCHAIN_MIDDLEWARE_POLICY_SETTING_KEY,
                tenant_id=record.tenant_id,
            )
        return ResolvedLangChainMiddlewarePolicy(
            policy=policy,
            source=source,
            setting_key=LANGCHAIN_MIDDLEWARE_POLICY_SETTING_KEY,
            tenant_id=record.tenant_id,
        )

    async def _runtime_settings_resolver(
        self,
        *,
        tenant_id: str,
    ) -> RuntimeSettingsResolver | None:
        if self._runtime_settings_store is None:
            return None
        records = list(await self._runtime_settings_store.list(tenant_id=tenant_id))
        if tenant_id != GLOBAL_TENANT_ID:
            records.extend(await self._runtime_settings_store.list(tenant_id=GLOBAL_TENANT_ID))
        return RuntimeSettingsResolver(records)

    async def _runtime_setting_middleware_policy(
        self,
        *,
        tenant_id: str,
    ) -> LangChainMiddlewarePolicy | None:
        resolved = await self._resolved_runtime_setting_middleware_policy(tenant_id=tenant_id)
        if not isinstance(resolved, ResolvedLangChainMiddlewarePolicy):
            return None
        return resolved.policy

    async def list_events(
        self,
        run_id: str,
        *,
        tenant_id: str | None = None,
        after_sequence: int = 0,
    ) -> list[RunEventRecord]:
        run_store = self._run_store
        if run_store is None:
            return []
        return await run_store.list_events(
            run_id=run_id,
            tenant_id=tenant_id,
            after_sequence=after_sequence,
        )

    async def resume_run(
        self,
        *,
        run_id: str,
        tenant_id: str,
        user_id: str,
        thread_id: str,
        checkpoint_ns: str,
        approval_id: str,
        approved: bool,
        reason: str | None = None,
        run_metadata: Mapping[str, Any] | None = None,
        input_text: str | None = None,
        run_user_id: str | None = None,
        run_status: str | None = None,
    ) -> RunResult:
        persisted_run: SessionRunRecord | None = None
        finder = getattr(self._run_store, "find_session", None)
        if finder is not None:
            persisted_run = cast(SessionRunRecord | None, await finder(run_id=run_id))
        metadata_source: Mapping[str, Any] = (
            persisted_run.metadata
            if persisted_run is not None
            else run_metadata
            if run_metadata is not None
            else {}
        )
        authoritative_thread_id = (
            persisted_run.thread_id if persisted_run is not None else thread_id
        )
        authoritative_checkpoint_ns = (
            persisted_run.checkpoint_ns if persisted_run is not None else checkpoint_ns
        )
        effective_metadata = run_metadata_with_defaults(
            dict(metadata_source),
            checkpoint_ns=authoritative_checkpoint_ns,
        )
        effective_input_text = (
            persisted_run.input_text
            if persisted_run is not None
            else input_text
            if input_text is not None
            else ""
        )
        effective_run_user_id = (
            persisted_run.user_id if persisted_run is not None else run_user_id or user_id
        )
        effective_run_status = persisted_run.status if persisted_run is not None else run_status
        resume_checkpoint_id = (
            optional_metadata_string(persisted_run.metadata.get("last_checkpoint_id"))
            if persisted_run is not None
            else None
        )
        if persisted_run is not None and (
            persisted_run.tenant_id != tenant_id
            or authoritative_thread_id != thread_id
            or authoritative_checkpoint_ns != checkpoint_ns
        ):
            return resume_failure_result(
                run_id=run_id,
                tenant_id=tenant_id,
                user_id=effective_run_user_id,
                thread_id=authoritative_thread_id,
                checkpoint_ns=authoritative_checkpoint_ns,
                provider=str(
                    effective_metadata.get("modelProvider") or self._settings.default_model_provider
                ),
                model=str(effective_metadata.get("model") or self._settings.default_model),
                reason="resume_checkpoint_provenance_mismatch",
            )
        thread_id = authoritative_thread_id
        checkpoint_ns = authoritative_checkpoint_ns
        runtime = str(effective_metadata.get("runtime") or "langgraph")
        provider = str(
            effective_metadata.get("modelProvider") or self._settings.default_model_provider
        )
        model = str(effective_metadata.get("model") or self._settings.default_model)
        if runtime not in ALLOWED_AGENT_RUNTIMES:
            return resume_failure_result(
                run_id=run_id,
                tenant_id=tenant_id,
                user_id=effective_run_user_id,
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                provider=provider,
                model=model,
                reason="unsupported_resume_runtime",
            )
        if (
            persisted_run is not None
            and effective_run_status == "interrupted"
            and resume_checkpoint_id is None
        ):
            return resume_failure_result(
                run_id=run_id,
                tenant_id=tenant_id,
                user_id=effective_run_user_id,
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                provider=provider,
                model=model,
                reason="resume_checkpoint_provenance_missing",
            )
        if runtime == "langchain_agent":
            return await self._resume_langchain_agent_run(
                run_id=run_id,
                tenant_id=tenant_id,
                resumed_by=user_id,
                run_user_id=effective_run_user_id,
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                checkpoint_id=resume_checkpoint_id,
                approval_id=approval_id,
                approved=approved,
                input_text=effective_input_text,
                run_metadata=effective_metadata,
                run_status=effective_run_status,
            )
        if effective_run_status != "interrupted":
            return resume_failure_result(
                run_id=run_id,
                tenant_id=tenant_id,
                user_id=effective_run_user_id,
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                provider=provider,
                model=model,
                reason=(
                    "run_state_unavailable"
                    if effective_run_status is None
                    else "run_not_interrupted"
                ),
            )
        if self._approval_store is None:
            return resume_failure_result(
                run_id=run_id,
                tenant_id=tenant_id,
                user_id=effective_run_user_id,
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                provider=provider,
                model=model,
                reason="approval_persistence_unavailable",
            )
        try:
            approval = await self._approval_store.find_approval(
                tenant_id=tenant_id,
                approval_id=approval_id,
            )
        except asyncio.CancelledError:
            await self._persist_external_run_cancellation(
                run_id=run_id,
                tenant_id=tenant_id,
                user_id=effective_run_user_id,
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                provider=provider,
                model=model,
                run_metadata=effective_metadata,
            )
            raise
        except Exception:
            return resume_failure_result(
                run_id=run_id,
                tenant_id=tenant_id,
                user_id=effective_run_user_id,
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                provider=provider,
                model=model,
                reason="approval_lookup_failed",
            )
        expected_status = "approved" if approved else "rejected"
        if approval is None or approval.run_id != run_id or approval.status != expected_status:
            return resume_failure_result(
                run_id=run_id,
                tenant_id=tenant_id,
                user_id=effective_run_user_id,
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                provider=provider,
                model=model,
                reason="approval_state_mismatch",
            )
        if not approval_resume_provenance_matches(
            approval,
            runtime="langgraph",
            thread_id=thread_id,
            checkpoint_ns=checkpoint_ns,
        ):
            return resume_failure_result(
                run_id=run_id,
                tenant_id=tenant_id,
                user_id=effective_run_user_id,
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                provider=provider,
                model=model,
                reason="approval_resume_provenance_mismatch",
            )
        try:
            tool_exposure = await self._enabled_tools_for_runtime(
                "langgraph",
                tenant_id=tenant_id,
                metadata=effective_metadata,
                approval_resume=True,
            )
        except asyncio.CancelledError:
            await self._persist_external_run_cancellation(
                run_id=run_id,
                tenant_id=tenant_id,
                user_id=effective_run_user_id,
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                provider=provider,
                model=model,
                run_metadata=effective_metadata,
            )
            raise
        except Exception:
            return resume_failure_result(
                run_id=run_id,
                tenant_id=tenant_id,
                user_id=effective_run_user_id,
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                provider=provider,
                model=model,
                reason="tool_policy_lookup_failed",
            )
        if approved and not approval_tool_matches_current_exposure(
            approval,
            tool_exposure.tools,
        ):
            return resume_failure_result(
                run_id=run_id,
                tenant_id=tenant_id,
                user_id=effective_run_user_id,
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                provider=provider,
                model=model,
                reason="approval_tool_not_active",
            )
        durable_decided_by = (approval.decided_by or "").strip()
        if not durable_decided_by:
            return resume_failure_result(
                run_id=run_id,
                tenant_id=tenant_id,
                user_id=effective_run_user_id,
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                provider=provider,
                model=model,
                reason="approval_decision_provenance_missing",
            )
        decision = ApprovalResumeDecision(
            approval_id=approval_id,
            approved=approved,
            decided_by=durable_decided_by,
            reason=approval.decision_reason,
        )
        try:
            resume_command = decision.as_langgraph_command()
        except ValueError:
            return resume_failure_result(
                run_id=run_id,
                tenant_id=tenant_id,
                user_id=effective_run_user_id,
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                provider=provider,
                model=model,
                reason="invalid_approval_decision",
            )
        run_store = self._run_store
        if run_store is None:
            return resume_failure_result(
                run_id=run_id,
                tenant_id=tenant_id,
                user_id=effective_run_user_id,
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                provider=provider,
                model=model,
                reason="resume_claim_unavailable",
            )
        if self._graph is None:
            return resume_failure_result(
                run_id=run_id,
                tenant_id=tenant_id,
                user_id=effective_run_user_id,
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                provider=provider,
                model=model,
                reason="resume_runtime_unavailable",
            )
        try:
            claimed = await run_store.claim_interrupted_resume(
                run_id=run_id,
                tenant_id=tenant_id,
                approval_id=approval_id,
                claimed_by=user_id,
                runtime="langgraph",
            )
        except asyncio.CancelledError:
            await self._persist_external_run_cancellation(
                run_id=run_id,
                tenant_id=tenant_id,
                user_id=effective_run_user_id,
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                provider=provider,
                model=model,
                run_metadata=effective_metadata,
            )
            raise
        if not claimed:
            return resume_failure_result(
                run_id=run_id,
                tenant_id=tenant_id,
                user_id=effective_run_user_id,
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                provider=provider,
                model=model,
                reason="resume_already_claimed",
            )
        timed_out = False
        guard_error: InputGuardBlocked | OutputGuardBlocked | None = None
        resume_error: Exception | None = None
        try:
            response = await asyncio.wait_for(
                self._graph.ainvoke(
                    resume_command,
                    config=langgraph_durable_config(
                        tenant_id=tenant_id,
                        thread_id=thread_id,
                        checkpoint_ns=checkpoint_ns,
                        checkpoint_id=resume_checkpoint_id,
                        run_name=LANGGRAPH_NATIVE_RESUME_RUN_NAME,
                        tags=LANGGRAPH_NATIVE_RUN_TAGS,
                        metadata=LANGGRAPH_NATIVE_CONFIG_METADATA,
                    ),
                ),
                timeout=self._settings.agent_run_timeout_ms / 1000,
            )
        except asyncio.CancelledError:
            await self._persist_external_run_cancellation(
                run_id=run_id,
                tenant_id=tenant_id,
                user_id=effective_run_user_id,
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                provider=provider,
                model=model,
                run_metadata=effective_metadata,
            )
            raise
        except TimeoutError:
            timed_out = True
            response = {}
        except (InputGuardBlocked, OutputGuardBlocked) as error:
            guard_error = error
            response = {}
        except Exception as error:
            resume_error = error
            response = {}
        response_text = ""
        native_interrupts: tuple[object, ...] = ()
        if isinstance(response, Mapping):
            typed_response = cast(Mapping[object, object], response)
            raw_response_text: object = typed_response.get("response_text")
            if isinstance(raw_response_text, str):
                response_text = raw_response_text
            native_interrupts = native_langgraph_interrupts(cast(Mapping[str, object], response))
        interrupted = bool(native_interrupts) and not timed_out
        provider_token_usage = (
            latest_provider_usage(
                dict(cast(Mapping[str, Any], response)),
                max_output_tokens=self._settings.max_output_tokens,
            )
            if isinstance(response, Mapping)
            else None
        )
        result = RunResult(
            run_id=run_id,
            tenant_id=tenant_id,
            user_id=effective_run_user_id,
            thread_id=thread_id,
            checkpoint_ns=checkpoint_ns,
            status=(
                "failed"
                if resume_error is not None
                else "timeout"
                if timed_out
                else "interrupted"
                if interrupted
                else "completed"
                if approved
                else "rejected"
            ),
            response=(
                "Agent run failed."
                if resume_error is not None
                else f"Agent run timed out after {self._settings.agent_run_timeout_ms}ms."
                if timed_out
                else "Agent run paused for approval."
                if interrupted
                else response_text
            ),
            provider=provider,
            model=model,
            token_usage=provider_token_usage
            or estimated_usage(
                effective_input_text,
                (
                    "Agent run failed."
                    if resume_error is not None
                    else f"Agent run timed out after {self._settings.agent_run_timeout_ms}ms."
                    if timed_out
                    else "Agent run paused for approval."
                    if interrupted
                    else response_text
                ),
                max_output_tokens=self._settings.max_output_tokens,
            ),
            response_metadata=(
                {
                    "approval_status": "pending",
                    "stop_reason": "langgraph_interrupt",
                }
                if interrupted
                else {"stop_reason": "runtime_error"}
                if resume_error is not None
                else metadata_from_graph_result(dict(cast(Mapping[str, Any], response)))
                if isinstance(response, Mapping) and not timed_out
                else {}
            ),
            interrupt_actions=extract_native_langgraph_interrupt_actions(native_interrupts),
        )
        if guard_error is not None:
            result = guard_block_result(
                guard_error,
                run_id=run_id,
                tenant_id=tenant_id,
                user_id=effective_run_user_id,
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                provider=provider,
                model=model,
                message=effective_input_text,
                max_output_tokens=self._settings.max_output_tokens,
            )
        else:
            result = replace(
                result,
                status=response_policy_terminal_status(
                    result.response_metadata,
                    default=result.status,
                ),
            )
        try:
            last_checkpoint_id = (
                await latest_checkpoint_id(
                    self._checkpointer,
                    config=langgraph_durable_config(
                        tenant_id=tenant_id,
                        thread_id=thread_id,
                        checkpoint_ns=checkpoint_ns,
                    ),
                )
                if result.status in {"completed", "interrupted"}
                else None
            )
        except asyncio.CancelledError:
            await self._persist_external_run_cancellation(
                run_id=run_id,
                tenant_id=tenant_id,
                user_id=effective_run_user_id,
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                provider=provider,
                model=model,
                run_metadata=effective_metadata,
            )
            raise
        if (
            result.status == "completed"
            and database_required_for_runtime(self._settings)
            and last_checkpoint_id is None
        ):
            result = missing_checkpoint_provenance_result(result)
        elif result.status == "interrupted" and last_checkpoint_id is None:
            result = unresumable_interrupt_result(
                result,
                reason="checkpoint_provenance_unavailable",
            )
        if result.status == "interrupted":
            try:
                result = await self._persist_interrupt_approval(
                    result,
                    tools=tool_exposure.tools,
                    runtime="langgraph",
                )
            except asyncio.CancelledError:
                await self._persist_external_run_cancellation(
                    run_id=run_id,
                    tenant_id=tenant_id,
                    user_id=effective_run_user_id,
                    thread_id=thread_id,
                    checkpoint_ns=checkpoint_ns,
                    provider=provider,
                    model=model,
                    run_metadata=effective_metadata,
                )
                raise
        result = await self._filter_invoke_result_response(
            result,
            tools_used=[],
            run_metadata=effective_metadata,
        )
        completed_metadata: dict[str, object] = {
            **effective_metadata,
            "resumed_from_run_id": run_id,
            "approval_id": approval_id,
            "checkpoint_ns": checkpoint_ns,
        }
        if last_checkpoint_id is not None:
            completed_metadata["last_checkpoint_id"] = last_checkpoint_id
        completed_metadata.update(public_run_metadata(result.response_metadata))
        completed_metadata.pop("resolvedToolProfileBudget", None)
        resolved_tool_profile_budget_metadata = tool_exposure.resolved_budget_metadata()
        if resolved_tool_profile_budget_metadata is not None:
            completed_metadata["resolvedToolProfileBudget"] = resolved_tool_profile_budget_metadata
        token_usage = token_usage_metadata(result.token_usage)
        if token_usage is not None:
            completed_metadata["tokenUsage"] = token_usage
        completion_transitioned = await self._record_invoke_completion(
            result=result,
            metadata=completed_metadata,
            run_metadata=effective_metadata,
            completion_events=()
            if resume_error is not None
            else (
                RunCompletionEvent(
                    event_type="run.resumed",
                    payload={
                        "approval_id": approval_id,
                        "approved": approved,
                        "decided_by": decision.decided_by,
                        "resumed_by": user_id,
                        "reason": decision.reason,
                        "runtime": "langgraph",
                    },
                ),
            ),
        )
        if completion_transitioned is False:
            return concurrent_cancellation_result(result)
        if resume_error is not None:
            await self._record_usage(result)
            raise resume_error
        await publish_run_lifecycle_event(
            self._run_lifecycle_publisher,
            {
                "event_type": "run.resumed",
                "run_id": run_id,
                "tenant_id": tenant_id,
                "user_id": effective_run_user_id,
                "decided_by": decision.decided_by,
                "resumed_by": user_id,
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "approval_id": approval_id,
                "approved": approved,
                "reason": decision.reason,
                "runtime": "langgraph",
            },
        )
        await self._record_usage(result)
        return result

    async def _resume_langchain_agent_run(
        self,
        *,
        run_id: str,
        tenant_id: str,
        resumed_by: str,
        run_user_id: str,
        thread_id: str,
        checkpoint_ns: str,
        checkpoint_id: str | None,
        approval_id: str,
        approved: bool,
        input_text: str,
        run_metadata: dict[str, Any],
        run_status: str | None,
    ) -> RunResult:
        provider = str(run_metadata.get("modelProvider") or self._settings.default_model_provider)
        model = str(run_metadata.get("model") or self._settings.default_model)
        if run_status != "interrupted":
            return resume_failure_result(
                run_id=run_id,
                tenant_id=tenant_id,
                user_id=run_user_id,
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                provider=provider,
                model=model,
                reason=("run_state_unavailable" if run_status is None else "run_not_interrupted"),
            )
        if self._approval_store is None:
            return resume_failure_result(
                run_id=run_id,
                tenant_id=tenant_id,
                user_id=run_user_id,
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                provider=provider,
                model=model,
                reason="approval_persistence_unavailable",
            )
        try:
            approval = await self._approval_store.find_approval(
                tenant_id=tenant_id,
                approval_id=approval_id,
            )
        except asyncio.CancelledError:
            await self._persist_external_run_cancellation(
                run_id=run_id,
                tenant_id=tenant_id,
                user_id=run_user_id,
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                provider=provider,
                model=model,
                run_metadata=run_metadata,
            )
            raise
        except Exception:
            return resume_failure_result(
                run_id=run_id,
                tenant_id=tenant_id,
                user_id=run_user_id,
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                provider=provider,
                model=model,
                reason="approval_lookup_failed",
            )
        expected_status = "approved" if approved else "rejected"
        if approval is None or approval.run_id != run_id or approval.status != expected_status:
            return resume_failure_result(
                run_id=run_id,
                tenant_id=tenant_id,
                user_id=run_user_id,
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                provider=provider,
                model=model,
                reason="approval_state_mismatch",
            )
        if not approval_resume_provenance_matches(
            approval,
            runtime="langchain_agent",
            thread_id=thread_id,
            checkpoint_ns=checkpoint_ns,
        ):
            return resume_failure_result(
                run_id=run_id,
                tenant_id=tenant_id,
                user_id=run_user_id,
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                provider=provider,
                model=model,
                reason="approval_resume_provenance_mismatch",
            )
        try:
            runtime_settings_resolver = (
                await self._runtime_settings_resolver(tenant_id=tenant_id)
                if "toolProfileBudget" not in run_metadata
                and "middlewarePolicy" not in run_metadata
                else None
            )
            tool_exposure = await self._enabled_tools_for_runtime(
                "langchain_agent",
                tenant_id=tenant_id,
                metadata=run_metadata,
                approval_resume=True,
                runtime_settings_resolver=runtime_settings_resolver,
            )
        except asyncio.CancelledError:
            await self._persist_external_run_cancellation(
                run_id=run_id,
                tenant_id=tenant_id,
                user_id=run_user_id,
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                provider=provider,
                model=model,
                run_metadata=run_metadata,
            )
            raise
        except Exception:
            return resume_failure_result(
                run_id=run_id,
                tenant_id=tenant_id,
                user_id=run_user_id,
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                provider=provider,
                model=model,
                reason="runtime_policy_lookup_failed",
            )
        if approved and not approval_tool_matches_current_exposure(
            approval,
            tool_exposure.tools,
        ):
            return resume_failure_result(
                run_id=run_id,
                tenant_id=tenant_id,
                user_id=run_user_id,
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                provider=provider,
                model=model,
                reason="approval_tool_not_active",
            )
        durable_decided_by = (approval.decided_by or "").strip()
        if not durable_decided_by:
            return resume_failure_result(
                run_id=run_id,
                tenant_id=tenant_id,
                user_id=run_user_id,
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                provider=provider,
                model=model,
                reason="approval_decision_provenance_missing",
            )
        decision_reason = approval.decision_reason
        decision = ApprovalResumeDecision(
            approval_id=approval_id,
            approved=approved,
            decided_by=durable_decided_by,
            reason=decision_reason,
        )
        try:
            resume_command = decision.as_langchain_hitl_command()
        except ValueError:
            return resume_failure_result(
                run_id=run_id,
                tenant_id=tenant_id,
                user_id=run_user_id,
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                provider=provider,
                model=model,
                reason="invalid_approval_decision",
            )
        tools = tool_exposure.tools
        structured_output = resolved_structured_output(run_metadata)
        try:
            middleware_resolution = await self._resolved_langchain_middleware_policy(
                run_metadata,
                tenant_id=tenant_id,
                runtime_settings_resolver=runtime_settings_resolver,
            )
        except asyncio.CancelledError:
            await self._persist_external_run_cancellation(
                run_id=run_id,
                tenant_id=tenant_id,
                user_id=run_user_id,
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                provider=provider,
                model=model,
                run_metadata=run_metadata,
            )
            raise
        middleware_policy = (
            middleware_resolution.policy
            if isinstance(middleware_resolution, ResolvedLangChainMiddlewarePolicy)
            else None
        )
        if self._run_store is None:
            return resume_failure_result(
                run_id=run_id,
                tenant_id=tenant_id,
                user_id=run_user_id,
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                provider=provider,
                model=model,
                reason="resume_claim_unavailable",
            )
        try:
            claimed = await self._run_store.claim_interrupted_resume(
                run_id=run_id,
                tenant_id=tenant_id,
                approval_id=approval_id,
                claimed_by=resumed_by,
                runtime="langchain_agent",
            )
        except asyncio.CancelledError:
            await self._persist_external_run_cancellation(
                run_id=run_id,
                tenant_id=tenant_id,
                user_id=run_user_id,
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                provider=provider,
                model=model,
                run_metadata=run_metadata,
            )
            raise
        if not claimed:
            return resume_failure_result(
                run_id=run_id,
                tenant_id=tenant_id,
                user_id=run_user_id,
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                provider=provider,
                model=model,
                reason="resume_already_claimed",
            )
        resume_error: Exception | None = None
        try:
            result = await run_once(
                input_text,
                self._settings,
                run_id=run_id,
                graph=self._graph,
                tenant_id=tenant_id,
                user_id=run_user_id,
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                checkpoint_id=checkpoint_id,
                provider=provider,
                model=model,
                system_prompt=optional_metadata_string(run_metadata.get("systemPrompt")),
                response_format=structured_output.response_format,
                structured_output_schema=structured_output.schema,
                fallback_models=optional_metadata_string_list(run_metadata.get("fallbackModels")),
                middleware_policy=middleware_policy,
                runtime="langchain_agent",
                tools=tools,
                tool_handler=self._tool_handler,
                tool_invocation_store=self._tool_invocation_store,
                checkpointer=self._checkpointer,
                graph_store=self._graph_store,
                integration_context=integration_context_from_metadata(run_metadata),
                context_manifest=optional_metadata_json_object(run_metadata.get("contextManifest")),
                resume_command=resume_command,
            )
        except asyncio.CancelledError:
            await self._persist_external_run_cancellation(
                run_id=run_id,
                tenant_id=tenant_id,
                user_id=run_user_id,
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                provider=provider,
                model=model,
                run_metadata=run_metadata,
            )
            raise
        except Exception as error:
            resume_error = error
            result = RunResult(
                run_id=run_id,
                tenant_id=tenant_id,
                user_id=run_user_id,
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                status="failed",
                response="Agent run failed.",
                provider=provider,
                model=model,
                token_usage=estimated_usage(
                    input_text,
                    "Agent run failed.",
                    max_output_tokens=self._settings.max_output_tokens,
                ),
                response_metadata={"stop_reason": "runtime_error"},
            )
        try:
            last_checkpoint_id = (
                await latest_checkpoint_id(
                    self._checkpointer,
                    config=langgraph_durable_config(
                        tenant_id=tenant_id,
                        thread_id=thread_id,
                        checkpoint_ns=checkpoint_ns,
                    ),
                )
                if result.status in {"completed", "interrupted"}
                else None
            )
        except asyncio.CancelledError:
            await self._persist_external_run_cancellation(
                run_id=run_id,
                tenant_id=tenant_id,
                user_id=run_user_id,
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                provider=provider,
                model=model,
                run_metadata=run_metadata,
            )
            raise
        if (
            result.status == "completed"
            and database_required_for_runtime(self._settings)
            and last_checkpoint_id is None
        ):
            result = missing_checkpoint_provenance_result(result)
        elif result.status == "interrupted" and last_checkpoint_id is None:
            result = unresumable_interrupt_result(
                result,
                reason="checkpoint_provenance_unavailable",
            )
        if result.status == "interrupted":
            try:
                result = await self._persist_interrupt_approval(
                    result,
                    tools=tools,
                    runtime="langchain_agent",
                )
            except asyncio.CancelledError:
                await self._persist_external_run_cancellation(
                    run_id=run_id,
                    tenant_id=tenant_id,
                    user_id=run_user_id,
                    thread_id=thread_id,
                    checkpoint_ns=checkpoint_ns,
                    provider=provider,
                    model=model,
                    run_metadata=run_metadata,
                )
                raise
        result = await self._filter_invoke_result_response(
            result,
            tools_used=[tool.qualified_name for tool in tools or []],
            run_metadata=run_metadata,
        )
        completed_metadata = {
            **run_metadata,
            "resumed_from_run_id": run_id,
            "approval_id": approval_id,
            "checkpoint_ns": checkpoint_ns,
        }
        if last_checkpoint_id is not None:
            completed_metadata["last_checkpoint_id"] = last_checkpoint_id
        completed_metadata.update(public_run_metadata(result.response_metadata))
        completed_metadata.pop("resolvedToolProfileBudget", None)
        resolved_tool_profile_budget_metadata = tool_exposure.resolved_budget_metadata()
        if resolved_tool_profile_budget_metadata is not None:
            completed_metadata["resolvedToolProfileBudget"] = resolved_tool_profile_budget_metadata
        token_usage = token_usage_metadata(result.token_usage)
        if token_usage is not None:
            completed_metadata["tokenUsage"] = token_usage
        completed_metadata.pop("langchainMiddlewarePolicy", None)
        if middleware_resolution is not None:
            completed_metadata["langchainMiddlewarePolicy"] = middleware_resolution.metadata()
        completion_transitioned = await self._record_invoke_completion(
            result=result,
            metadata=completed_metadata,
            run_metadata=run_metadata,
            completion_events=()
            if resume_error is not None
            else (
                RunCompletionEvent(
                    event_type="run.resumed",
                    payload={
                        "approval_id": approval_id,
                        "approved": approved,
                        "decided_by": decision.decided_by,
                        "resumed_by": resumed_by,
                        "reason": decision_reason,
                        "runtime": "langchain_agent",
                    },
                ),
            ),
        )
        if completion_transitioned is False:
            return concurrent_cancellation_result(result)
        if resume_error is not None:
            await self._record_usage(result)
            raise resume_error
        await publish_run_lifecycle_event(
            self._run_lifecycle_publisher,
            {
                "event_type": "run.resumed",
                "run_id": run_id,
                "tenant_id": tenant_id,
                "user_id": run_user_id,
                "decided_by": decision.decided_by,
                "resumed_by": resumed_by,
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "approval_id": approval_id,
                "approved": approved,
                "reason": decision_reason,
                "runtime": "langchain_agent",
            },
        )
        await self._record_usage(result)
        return result

    async def cancel_run(
        self,
        *,
        run_id: str,
        tenant_id: str,
        user_id: str,
        thread_id: str,
        checkpoint_ns: str,
        reason: str | None = None,
    ) -> RunResult:
        result = RunResult(
            run_id=run_id,
            tenant_id=tenant_id,
            user_id=user_id,
            thread_id=thread_id,
            checkpoint_ns=checkpoint_ns,
            status="cancelled",
            response="Run cancelled.",
            provider=self._settings.default_model_provider,
            model=self._settings.default_model,
        )
        if self._run_store is not None:
            metadata = {
                "cancelled_by": user_id,
                "cancel_reason": reason or "user_requested_cancellation",
                "checkpoint_ns": checkpoint_ns,
            }
            transitioned = await self._run_store.record_cancelled_if_active(
                result=result,
                metadata=metadata,
            )
            if not transitioned:
                raise RunCancellationConflict("run is not running")
            await publish_run_lifecycle_event(
                self._run_lifecycle_publisher,
                {
                    "event_type": "run.cancelled",
                    "run_id": run_id,
                    "tenant_id": tenant_id,
                    "user_id": user_id,
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "reason": metadata["cancel_reason"],
                },
            )
        return result

    async def _persist_external_run_cancellation(
        self,
        *,
        run_id: str,
        tenant_id: str,
        user_id: str,
        thread_id: str,
        checkpoint_ns: str,
        provider: str,
        model: str,
        run_metadata: Mapping[str, Any],
    ) -> None:
        await self._persist_external_cancellation(
            run_id=run_id,
            tenant_id=tenant_id,
            user_id=user_id,
            thread_id=thread_id,
            checkpoint_ns=checkpoint_ns,
            provider=provider,
            model=model,
            run_metadata=run_metadata,
            reason="external_run_cancellation",
            response="Agent run cancelled.",
        )

    async def _persist_external_stream_cancellation(
        self,
        *,
        run_id: str,
        tenant_id: str,
        user_id: str,
        thread_id: str,
        checkpoint_ns: str,
        provider: str,
        model: str,
        run_metadata: Mapping[str, Any],
    ) -> None:
        await self._persist_external_cancellation(
            run_id=run_id,
            tenant_id=tenant_id,
            user_id=user_id,
            thread_id=thread_id,
            checkpoint_ns=checkpoint_ns,
            provider=provider,
            model=model,
            run_metadata=run_metadata,
            reason="external_stream_cancellation",
            response="Agent stream cancelled.",
        )

    async def _persist_external_cancellation(
        self,
        *,
        run_id: str,
        tenant_id: str,
        user_id: str,
        thread_id: str,
        checkpoint_ns: str,
        provider: str,
        model: str,
        run_metadata: Mapping[str, Any],
        reason: str,
        response: str,
    ) -> None:
        result = RunResult(
            run_id=run_id,
            tenant_id=tenant_id,
            user_id=user_id,
            thread_id=thread_id,
            checkpoint_ns=checkpoint_ns,
            status="cancelled",
            response=response,
            provider=provider,
            model=model,
            response_metadata={"stop_reason": reason},
        )
        cancellation_persisted = self._run_store is None
        if self._run_store is not None:
            try:
                cancellation_persisted = await self._run_store.record_cancelled_if_running(
                    result=result,
                    metadata={
                        **run_metadata,
                        "checkpoint_ns": checkpoint_ns,
                        "cancelled_by": user_id,
                        "cancel_reason": reason,
                    },
                )
            except Exception:
                logger.warning(
                    "external run cancellation persistence failed",
                    extra={
                        "run_id": run_id,
                        "tenant_id": tenant_id,
                    },
                )
        if cancellation_persisted:
            await publish_run_lifecycle_event(
                self._run_lifecycle_publisher,
                {
                    "event_type": "run.cancelled",
                    "run_id": run_id,
                    "tenant_id": tenant_id,
                    "user_id": user_id,
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "reason": reason,
                },
            )

    async def stream_run(
        self,
        message: str,
        *,
        tenant_id: str = "local",
        user_id: str = "anonymous",
        trusted_user_groups: tuple[str, ...] = (),
        thread_id: str | None = None,
        checkpoint_ns: str | None = None,
        metadata: dict[str, Any] | None = None,
        checkpoint_fork: TrustedCheckpointFork | None = None,
    ) -> AsyncIterator[AgentStreamEvent]:
        run_id = new_id("run")
        actual_thread_id = thread_id or self._settings.default_thread_id
        actual_checkpoint_ns = checkpoint_ns or self._settings.default_checkpoint_ns
        trace_id = new_id("trace")
        run_metadata = run_metadata_with_defaults(
            metadata,
            checkpoint_ns=actual_checkpoint_ns,
            streaming=True,
            checkpoint_fork=checkpoint_fork,
        )
        provider = str(run_metadata.get("modelProvider") or self._settings.default_model_provider)
        model = str(run_metadata.get("model") or self._settings.default_model)
        if self._run_store is not None:
            try:
                await self._run_store.record_started(
                    run_id=run_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    thread_id=actual_thread_id,
                    checkpoint_ns=actual_checkpoint_ns,
                    input_text=message,
                    metadata=run_metadata,
                )
            except asyncio.CancelledError:
                await self._persist_external_stream_cancellation(
                    run_id=run_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    thread_id=actual_thread_id,
                    checkpoint_ns=actual_checkpoint_ns,
                    provider=provider,
                    model=model,
                    run_metadata=run_metadata,
                )
                raise
        sequence = 1
        started = AgentStreamEvent(
            run_id=run_id,
            sequence=sequence,
            event_type="run.stream.started",
            graph_node="graph",
            trace_id=trace_id,
        )
        await self.record_stream_event(started, tenant_id=tenant_id)
        try:
            yield started
        except GeneratorExit:
            await self._persist_external_stream_cancellation(
                run_id=run_id,
                tenant_id=tenant_id,
                user_id=user_id,
                thread_id=actual_thread_id,
                checkpoint_ns=actual_checkpoint_ns,
                provider=provider,
                model=model,
                run_metadata=run_metadata,
            )
            raise
        runtime = str(run_metadata.get("runtime") or "langgraph")
        if runtime not in ALLOWED_AGENT_RUNTIMES:
            result = RunResult(
                run_id=run_id,
                tenant_id=tenant_id,
                user_id=user_id,
                thread_id=actual_thread_id,
                checkpoint_ns=actual_checkpoint_ns,
                status="rejected",
                response="Unsupported agent runtime.",
                provider=provider,
                model=model,
            )
            result = await self._filter_result_response(result, tools_used=[])
            if self._run_store is not None:
                completion_transitioned = await self._run_store.record_completed(
                    result=result,
                    metadata={
                        **run_metadata,
                        "checkpoint_ns": result.checkpoint_ns,
                        "rejection_reason": "unsupported_runtime",
                    },
                )
                if completion_transitioned is False:
                    return
            completed = AgentStreamEvent(
                run_id=run_id,
                sequence=sequence + 1,
                event_type="run.stream.completed",
                graph_node="graph",
                trace_id=trace_id,
                payload=stream_completion_payload(result),
            )
            await self.record_stream_event(completed, tenant_id=tenant_id)
            yield completed
            return
        if runtime not in ALLOWED_STREAMING_AGENT_RUNTIMES:
            result = RunResult(
                run_id=run_id,
                tenant_id=tenant_id,
                user_id=user_id,
                thread_id=actual_thread_id,
                checkpoint_ns=actual_checkpoint_ns,
                status="rejected",
                response=f"Unsupported streaming agent runtime: {runtime}.",
                provider=provider,
                model=model,
            )
            result = await self._filter_result_response(result, tools_used=[])
            if self._run_store is not None:
                completion_transitioned = await self._run_store.record_completed(
                    result=result,
                    metadata={
                        **run_metadata,
                        "checkpoint_ns": result.checkpoint_ns,
                        "rejection_reason": "unsupported_streaming_runtime",
                    },
                )
                if completion_transitioned is False:
                    return
            completed = AgentStreamEvent(
                run_id=run_id,
                sequence=sequence + 1,
                event_type="run.stream.completed",
                graph_node="graph",
                trace_id=trace_id,
                payload=stream_completion_payload(result),
            )
            await self.record_stream_event(completed, tenant_id=tenant_id)
            yield completed
            return
        structured_output = resolved_structured_output(run_metadata)
        checkpoint_replay = checkpoint_replay_resolution(
            checkpoint_fork,
            target_thread_id=actual_thread_id,
            target_checkpoint_ns=actual_checkpoint_ns,
        )
        response_parts: list[str] = []
        native_final_response_text: str | None = None
        native_final_response_metadata: dict[str, object] = {}
        native_final_result_observed = False
        provider_token_usage: TokenUsage | None = None
        status = "completed"
        response_text = ""
        response_metadata: dict[str, object] = {}
        stream_error: Exception | None = None
        runtime_tools: list[ToolSpec] | None = None
        tool_exposure = ToolExposure(tools=None)
        runtime_settings_resolver: RuntimeSettingsResolver | None = None
        resolved_middleware_policy: LangChainMiddlewarePolicyResolution | None = None
        langchain_middleware_chain: dict[str, object] | None = None
        langchain_tool_messages: list[ToolMessage] = []
        langchain_structured_response: str | None = None
        langchain_context_manifest: Mapping[str, object] | None = (
            optional_metadata_json_object(run_metadata.get("contextManifest"))
            if runtime == "langchain_agent"
            else None
        )
        interrupt_actions: tuple[LangChainInterruptAction, ...] = ()
        observed_interrupt_actions: tuple[LangChainInterruptAction, ...] | None = None
        pending_approval_event: AgentStreamEvent | None = None
        try:
            async with asyncio.timeout(self._settings.agent_run_timeout_ms / 1000):
                checkpoint_replay = await materialize_checkpoint_replay(
                    self._checkpointer,
                    tenant_id=tenant_id,
                    checkpoint_fork=checkpoint_fork,
                    target_runtime=runtime,
                    target_graph_profile=optional_metadata_string(run_metadata.get("graphProfile")),
                    resolution=checkpoint_replay,
                    target_thread_id=actual_thread_id,
                    target_checkpoint_ns=actual_checkpoint_ns,
                )
                if checkpoint_replay.blocked:
                    status = "failed"
                    response_text = "Checkpoint fork could not be prepared safely."
                    response_metadata = {"stop_reason": "checkpoint_fork_failed"}
                    raise CheckpointForkStreamRejected()
                config = langgraph_durable_config(
                    tenant_id=tenant_id,
                    thread_id=actual_thread_id,
                    checkpoint_ns=actual_checkpoint_ns,
                    checkpoint_id=checkpoint_replay.checkpoint_id,
                    run_name=LANGGRAPH_NATIVE_STREAM_RUN_NAME,
                    tags=LANGGRAPH_NATIVE_RUN_TAGS,
                    metadata=LANGGRAPH_NATIVE_CONFIG_METADATA,
                )
                if runtime == "langchain_agent" and (
                    "toolProfileBudget" not in run_metadata
                    and "middlewarePolicy" not in run_metadata
                ):
                    runtime_settings_resolver = await self._runtime_settings_resolver(
                        tenant_id=tenant_id
                    )
                tool_exposure = await self._enabled_tools_for_runtime(
                    runtime,
                    tenant_id=tenant_id,
                    metadata=run_metadata,
                    runtime_settings_resolver=runtime_settings_resolver,
                )
                runtime_tools = tool_exposure.tools
                research_block_plan = blocked_research_plan_from_tool_exposure(
                    run_metadata,
                    tool_exposure,
                    message=message,
                )
                if research_block_plan is not None:
                    status = "rejected"
                    response_text = (
                        "Research profile requires Rag:hybrid_search, but that tool is not active."
                    )
                    response_metadata = {
                        "stop_reason": "forced_tool_unavailable",
                        "research_plan": research_block_plan,
                    }
                    raise ResearchStreamRejected()
                if runtime == "langchain_agent":
                    resolved_middleware_policy = await self._resolved_langchain_middleware_policy(
                        run_metadata,
                        tenant_id=tenant_id,
                        runtime_settings_resolver=runtime_settings_resolver,
                    )
                    middleware_policy = (
                        resolved_middleware_policy.policy
                        if isinstance(resolved_middleware_policy, ResolvedLangChainMiddlewarePolicy)
                        else None
                    )
                    fallback_models = optional_metadata_string_list(
                        run_metadata.get("fallbackModels")
                    )
                    interrupt_on_tools = approval_required_tool_names(runtime_tools)
                    langchain_middleware_chain = planned_langchain_middleware_chain_metadata(
                        self._settings,
                        interrupt_on_tools=interrupt_on_tools,
                        fallback_models=fallback_models,
                        policy=middleware_policy,
                    )
                    raw_events = stream_langchain_agent_events(
                        message,
                        self._settings,
                        provider=provider,
                        model=model,
                        thread_id=actual_thread_id,
                        checkpoint_ns=actual_checkpoint_ns,
                        checkpoint_id=checkpoint_replay.checkpoint_id,
                        system_prompt=optional_metadata_string(run_metadata.get("systemPrompt")),
                        tools=runtime_tools,
                        tool_handler=self._tool_handler,
                        tool_invocation_store=self._tool_invocation_store,
                        tenant_id=tenant_id,
                        user_id=user_id,
                        trusted_user_groups=trusted_user_groups,
                        run_id=run_id,
                        response_format=structured_output.response_format,
                        structured_output_schema=structured_output.schema,
                        checkpointer=self._checkpointer,
                        graph_store=self._graph_store,
                        fallback_models=fallback_models,
                        middleware_policy=middleware_policy,
                        integration_context=integration_context_from_metadata(run_metadata),
                        context_manifest=optional_metadata_json_object(
                            run_metadata.get("contextManifest")
                        ),
                    )
                else:
                    graph = self._graph
                    if graph is None:
                        graph = run_once_graph_adapter()
                    graph_profile = optional_metadata_string(run_metadata.get("graphProfile"))
                    state = initial_reactor_state(
                        run_id=run_id,
                        tenant_id=tenant_id,
                        user_id=user_id,
                        trusted_user_groups=trusted_user_groups,
                        messages=[HumanMessage(content=message)],
                        max_tool_calls=(
                            None if graph_profile is not None else self._settings.max_tool_calls
                        ),
                        checkpoint_ns=actual_checkpoint_ns,
                        request_system_prompt=optional_metadata_string(
                            run_metadata.get("systemPrompt")
                        ),
                        model_provider=provider,
                        selected_model=model,
                        graph_profile=graph_profile,
                        integration_context=integration_context_from_metadata(run_metadata),
                        active_tools=[tool.qualified_name for tool in runtime_tools]
                        if runtime_tools is not None
                        else None,
                        active_tool_specs=tool_state_specs(runtime_tools),
                    )
                    if structured_output.response_format is not None:
                        state["response_format"] = structured_output.response_format
                    if structured_output.schema is not None:
                        state["response_schema"] = structured_output.schema
                    raw_events = graph.astream_events(
                        state,
                        config=config,
                        version=LANGCHAIN_RAW_STREAM_EVENTS_VERSION,
                    )
                async for raw_event in raw_events:
                    if runtime == "langchain_agent":
                        langchain_tool_messages.extend(langchain_v2_stream_tool_messages(raw_event))
                        structured_response = langchain_v2_stream_structured_response(
                            raw_event,
                            structured_output_schema=structured_output.schema,
                        )
                        if structured_response is not None:
                            if langchain_structured_response is None:
                                langchain_structured_response = structured_response
                            elif structured_response != langchain_structured_response:
                                raise StructuredResponseStreamConflict()
                    provider_token_usage = (
                        stream_provider_usage(
                            raw_event,
                            max_output_tokens=self._settings.max_output_tokens,
                        )
                        or provider_token_usage
                    )
                    if runtime == "langgraph":
                        native_result = native_graph_stream_result(raw_event)
                        if native_result is not None:
                            final_text = native_result.get("response_text")
                            candidate_text = final_text if isinstance(final_text, str) else None
                            candidate_metadata = metadata_from_graph_result(dict(native_result))
                            if native_final_result_observed and (
                                candidate_text != native_final_response_text
                                or candidate_metadata != native_final_response_metadata
                            ):
                                raise NativeGraphResultStreamConflict()
                            native_final_response_text = candidate_text
                            native_final_response_metadata = candidate_metadata
                            native_final_result_observed = True
                    if langchain_v2_stream_interrupt_lineage_invalid(raw_event):
                        raise InterruptStreamLineageInvalid()
                    if langchain_v2_stream_interrupt_payload_invalid(raw_event):
                        raise InterruptStreamPayloadInvalid()
                    raw_interrupts = langchain_v2_stream_interrupts(raw_event)
                    if raw_interrupts:
                        if runtime == "langchain_agent":
                            current_interrupt_actions = extract_langchain_interrupt_actions(
                                raw_interrupts
                            )
                        else:
                            current_interrupt_actions = extract_native_langgraph_interrupt_actions(
                                raw_interrupts
                            )
                        if len(current_interrupt_actions) != 1:
                            raise InterruptStreamActionInvalid()
                        if observed_interrupt_actions is None:
                            observed_interrupt_actions = current_interrupt_actions
                            interrupt_actions = current_interrupt_actions
                        elif current_interrupt_actions != observed_interrupt_actions:
                            raise InterruptStreamConflict()
                        status = "interrupted"
                    if runtime == "langchain_agent":
                        stream_event = langchain_v2_stream_event_to_agent_event(
                            raw_event,
                            run_id=run_id,
                            sequence=sequence + 1,
                            fallback_trace_id=trace_id,
                        )
                    else:
                        stream_event = langgraph_stream_event_to_agent_event(
                            raw_event,
                            run_id=run_id,
                            sequence=sequence + 1,
                            fallback_trace_id=trace_id,
                        )
                    if stream_event is None:
                        continue
                    if stream_event.event_type == "run.stream.token":
                        text = stream_event.payload.get("text")
                        if isinstance(text, str):
                            response_parts.append(text)
                        continue
                    stream_event = await self._filter_stream_event_payload(
                        stream_event,
                        tenant_id=tenant_id,
                        user_id=user_id,
                    )
                    if stream_event.event_type == "run.stream.approval":
                        pending_approval_event = stream_event
                        continue
                    sequence = stream_event.sequence
                    await self.record_stream_event(stream_event, tenant_id=tenant_id)
                    yield stream_event
                if runtime == "langchain_agent":
                    langchain_context_manifest = context_manifest_with_runtime_rag_citations(
                        langchain_context_manifest,
                        messages=langchain_tool_messages,
                    )
                response_text = (
                    native_final_response_text
                    if runtime == "langgraph" and native_final_response_text is not None
                    else langchain_structured_response
                    if runtime == "langchain_agent" and langchain_structured_response is not None
                    else "".join(response_parts)
                )
                if status == "interrupted":
                    response_text = "Agent run paused for approval."
                    response_metadata = {
                        "approval_status": "pending",
                        "stop_reason": (
                            "langchain_interrupt"
                            if runtime == "langchain_agent"
                            else "langgraph_interrupt"
                        ),
                    }
                elif runtime == "langchain_agent":
                    boundary_result = await enforce_structured_response_boundary_with_metadata(
                        response_text,
                        response_format=structured_output.response_format,
                        structured_output_schema=structured_output.schema,
                        context_manifest=langchain_context_manifest,
                    )
                    response_text = boundary_result.response
                    response_metadata = boundary_result.metadata
                    status = response_policy_terminal_status(
                        response_metadata,
                        default=status,
                    )
                    if langchain_middleware_chain is not None:
                        response_metadata["langchainMiddlewareChain"] = langchain_middleware_chain
                else:
                    response_metadata = native_final_response_metadata
                    status = response_policy_terminal_status(
                        response_metadata,
                        default=status,
                    )
        except asyncio.CancelledError:
            await self._persist_external_stream_cancellation(
                run_id=run_id,
                tenant_id=tenant_id,
                user_id=user_id,
                thread_id=actual_thread_id,
                checkpoint_ns=actual_checkpoint_ns,
                provider=provider,
                model=model,
                run_metadata=run_metadata,
            )
            raise
        except TimeoutError:
            status = "timeout"
            response_text = f"Agent stream timed out after {self._settings.agent_run_timeout_ms}ms."
            response_metadata = {}
        except ResearchStreamRejected:
            pass
        except CheckpointForkStreamRejected:
            pass
        except InterruptStreamConflict:
            status = "failed"
            response_text = "Agent stream failed because interrupt frames conflicted."
            response_metadata = {"stop_reason": "interrupt_stream_conflict"}
            interrupt_actions = ()
        except InterruptStreamLineageInvalid:
            status = "failed"
            response_text = "Agent stream failed because interrupt lineage was invalid."
            response_metadata = {"stop_reason": "interrupt_stream_lineage_invalid"}
            interrupt_actions = ()
        except InterruptStreamPayloadInvalid:
            status = "failed"
            response_text = "Agent stream failed because interrupt payload was invalid."
            response_metadata = {"stop_reason": "interrupt_stream_payload_invalid"}
            interrupt_actions = ()
        except InterruptStreamActionInvalid:
            status = "failed"
            response_text = "Agent stream failed because interrupt actions were invalid."
            response_metadata = {"stop_reason": "interrupt_stream_action_invalid"}
            interrupt_actions = ()
        except StructuredResponseStreamConflict:
            status = "failed"
            response_text = "Agent stream failed because root structured responses conflicted."
            response_metadata = {"stop_reason": "structured_response_stream_conflict"}
        except NativeGraphResultStreamConflict:
            status = "failed"
            response_text = "Agent stream failed because root graph results conflicted."
            response_metadata = {"stop_reason": "native_graph_result_stream_conflict"}
        except Exception as error:
            stream_error = error
            status = "failed"
            response_text = "Agent stream failed."
            response_metadata = {}
        if runtime == "langchain_agent":
            tool_output_guard = langchain_tool_output_guard(langchain_tool_messages)
            if tool_output_guard is not None:
                guard_metadata, model_visible_outputs = tool_output_guard
                findings = cast(list[str], guard_metadata["findings"])
                if findings:
                    response_metadata["tool_output_guard_findings"] = findings
                response_metadata["contextManifest"] = context_manifest_with_tool_output_guard(
                    langchain_context_manifest,
                    metadata=guard_metadata,
                    model_visible_outputs=model_visible_outputs,
                )
                guard_error_code = tool_output_guard_error_code(guard_metadata)
                if guard_error_code is not None:
                    status = "rejected"
                    response_text = "Response blocked by tool output guard policy."
                    response_metadata.pop("approval_status", None)
                    response_metadata.update(
                        {
                            "stop_reason": "tool_output_guard_blocked",
                            "tool_output_guard_error_code": guard_error_code,
                            "tool_output_guard_status": "blocked",
                        }
                    )
                    interrupt_actions = ()
                    pending_approval_event = None
        result = RunResult(
            run_id=run_id,
            tenant_id=tenant_id,
            user_id=user_id,
            thread_id=actual_thread_id,
            checkpoint_ns=actual_checkpoint_ns,
            status=status,
            response=response_text,
            provider=provider,
            model=model,
            token_usage=provider_token_usage
            or estimated_usage(
                message,
                response_text,
                max_output_tokens=self._settings.max_output_tokens,
            ),
            response_metadata=response_metadata,
            interrupt_actions=interrupt_actions,
        )
        try:
            last_checkpoint_id = (
                await latest_checkpoint_id(
                    self._checkpointer,
                    config=langgraph_durable_config(
                        tenant_id=tenant_id,
                        thread_id=actual_thread_id,
                        checkpoint_ns=actual_checkpoint_ns,
                    ),
                )
                if result.status in {"completed", "interrupted"} and self._run_store is not None
                else None
            )
        except asyncio.CancelledError:
            await self._persist_external_stream_cancellation(
                run_id=run_id,
                tenant_id=tenant_id,
                user_id=user_id,
                thread_id=actual_thread_id,
                checkpoint_ns=actual_checkpoint_ns,
                provider=provider,
                model=model,
                run_metadata=run_metadata,
            )
            raise
        if (
            result.status == "completed"
            and database_required_for_runtime(self._settings)
            and last_checkpoint_id is None
        ):
            result = missing_checkpoint_provenance_result(result)
        elif result.status == "interrupted" and last_checkpoint_id is None:
            result = unresumable_interrupt_result(
                result,
                reason="checkpoint_provenance_unavailable",
            )
        elif result.status == "interrupted":
            try:
                result = await self._persist_interrupt_approval(
                    result,
                    tools=runtime_tools,
                    runtime=runtime,
                )
            except asyncio.CancelledError:
                await self._persist_external_stream_cancellation(
                    run_id=run_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    thread_id=actual_thread_id,
                    checkpoint_ns=actual_checkpoint_ns,
                    provider=provider,
                    model=model,
                    run_metadata=run_metadata,
                )
                raise
        try:
            result = await self._filter_result_response(
                result,
                tools_used=[tool.qualified_name for tool in runtime_tools or []],
            )
        except asyncio.CancelledError:
            await self._persist_external_stream_cancellation(
                run_id=run_id,
                tenant_id=tenant_id,
                user_id=user_id,
                thread_id=actual_thread_id,
                checkpoint_ns=actual_checkpoint_ns,
                provider=provider,
                model=model,
                run_metadata=run_metadata,
            )
            raise
        if result.status == "interrupted" and pending_approval_event is not None:
            approval_id = result.response_metadata.get("approval_id")
            if isinstance(approval_id, str):
                pending_approval_event = replace(
                    pending_approval_event,
                    payload={**pending_approval_event.payload, "approval_id": approval_id},
                )
            sequence = pending_approval_event.sequence
            try:
                await self.record_stream_event(pending_approval_event, tenant_id=tenant_id)
            except asyncio.CancelledError:
                await self._persist_external_stream_cancellation(
                    run_id=run_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    thread_id=actual_thread_id,
                    checkpoint_ns=actual_checkpoint_ns,
                    provider=provider,
                    model=model,
                    run_metadata=run_metadata,
                )
                raise
            try:
                yield pending_approval_event
            except GeneratorExit:
                await self._persist_external_stream_cancellation(
                    run_id=run_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    thread_id=actual_thread_id,
                    checkpoint_ns=actual_checkpoint_ns,
                    provider=provider,
                    model=model,
                    run_metadata=run_metadata,
                )
                raise
        if result.status == "completed" and result.response:
            sequence += 1
            token = AgentStreamEvent(
                run_id=run_id,
                sequence=sequence,
                event_type="run.stream.token",
                graph_node="model",
                trace_id=trace_id,
                payload={"text": result.response},
            )
            try:
                await self.record_stream_event(token, tenant_id=tenant_id)
            except asyncio.CancelledError:
                await self._persist_external_stream_cancellation(
                    run_id=run_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    thread_id=actual_thread_id,
                    checkpoint_ns=actual_checkpoint_ns,
                    provider=provider,
                    model=model,
                    run_metadata=run_metadata,
                )
                raise
            try:
                yield token
            except GeneratorExit:
                await self._persist_external_stream_cancellation(
                    run_id=run_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    thread_id=actual_thread_id,
                    checkpoint_ns=actual_checkpoint_ns,
                    provider=provider,
                    model=model,
                    run_metadata=run_metadata,
                )
                raise
        if self._run_store is not None:
            completed_metadata = {**run_metadata, "checkpoint_ns": result.checkpoint_ns}
            completed_metadata.update(public_run_metadata(result.response_metadata))
            if last_checkpoint_id is not None:
                completed_metadata["last_checkpoint_id"] = last_checkpoint_id
            token_usage = token_usage_metadata(result.token_usage)
            if token_usage is not None:
                completed_metadata["tokenUsage"] = token_usage
            stop_reason = result.response_metadata.get("stop_reason")
            if result.status == "rejected" and isinstance(stop_reason, str):
                completed_metadata["rejection_reason"] = stop_reason
            if checkpoint_replay.metadata is not None:
                completed_metadata["checkpointReplay"] = checkpoint_replay.metadata
            if runtime == "langchain_agent" and resolved_middleware_policy is not None:
                completed_metadata["langchainMiddlewarePolicy"] = (
                    resolved_middleware_policy.metadata()
                )
            structured_output_metadata = structured_output.metadata()
            if structured_output_metadata is not None:
                completed_metadata["structuredOutput"] = structured_output_metadata
            resolved_tool_profile_budget_metadata = tool_exposure.resolved_budget_metadata()
            if resolved_tool_profile_budget_metadata is not None:
                completed_metadata["resolvedToolProfileBudget"] = (
                    resolved_tool_profile_budget_metadata
                )
            try:
                completion_transitioned = await self._run_store.record_completed(
                    result=result,
                    metadata=completed_metadata,
                )
            except asyncio.CancelledError:
                await self._persist_external_stream_cancellation(
                    run_id=run_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    thread_id=actual_thread_id,
                    checkpoint_ns=actual_checkpoint_ns,
                    provider=provider,
                    model=model,
                    run_metadata=run_metadata,
                )
                raise
            if completion_transitioned is False:
                return
        await self._record_usage(result)
        completed = AgentStreamEvent(
            run_id=run_id,
            sequence=sequence + 1,
            event_type="run.stream.completed",
            graph_node="graph",
            trace_id=trace_id,
            payload=stream_completion_payload(result),
        )
        await self.record_stream_event(completed, tenant_id=tenant_id)
        yield completed
        if stream_error is not None:
            raise stream_error

    async def record_stream_event(self, event: AgentStreamEvent, tenant_id: str = "local") -> None:
        if self._run_store is None:
            return
        await self._run_store.record_event(
            run_id=event.run_id,
            tenant_id=tenant_id,
            sequence=event.sequence,
            event_type=event.event_type,
            payload=event.as_payload(),
        )

    async def _record_usage(self, result: RunResult) -> None:
        if result.token_usage is None:
            return
        usage = result.token_usage
        estimated_cost_usd = Decimal("0")
        record_model_usage_metrics(
            provider=result.provider,
            model=result.model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
            estimated_cost_usd=estimated_cost_usd,
        )
        if self._usage_ledger is None:
            return
        try:
            await maybe_await(
                self._usage_ledger.record(
                    UsageLedgerRecord(
                        tenant_id=result.tenant_id,
                        run_id=result.run_id,
                        provider=result.provider,
                        model=result.model,
                        step_type="model",
                        prompt_tokens=usage.input_tokens,
                        cached_tokens=usage.cached_tokens,
                        completion_tokens=usage.output_tokens,
                        reasoning_tokens=usage.reasoning_tokens,
                        total_tokens=usage.total_tokens,
                        estimated_cost_usd=estimated_cost_usd,
                        occurred_at=datetime.now(UTC),
                    )
                )
            )
        except Exception:
            return


async def maybe_await[T](value: T) -> T:
    if isawaitable(value):
        return cast(T, await value)
    return value


def optional_metadata_string(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def checkpoint_replay_resolution(
    checkpoint_fork: TrustedCheckpointFork | None,
    *,
    target_thread_id: str,
    target_checkpoint_ns: str,
) -> CheckpointReplayResolution:
    if checkpoint_fork is None:
        return CheckpointReplayResolution()
    requested_checkpoint_id = optional_metadata_string(checkpoint_fork.source_checkpoint_id)
    if requested_checkpoint_id is None:
        return CheckpointReplayResolution(
            metadata={
                "status": "ignored",
                "reason": "missing_checkpoint_id",
                "source": "checkpoint_fork",
                "targetThreadId": target_thread_id,
                "targetCheckpointNs": target_checkpoint_ns,
            }
        )
    if checkpoint_fork.target_thread_id != target_thread_id:
        return CheckpointReplayResolution(
            metadata={
                "status": "ignored",
                "reason": "fork_target_mismatch",
                "source": "checkpoint_fork",
                "requestedCheckpointId": requested_checkpoint_id,
                "targetThreadId": target_thread_id,
                "targetCheckpointNs": target_checkpoint_ns,
                "metadataTargetThreadId": checkpoint_fork.target_thread_id,
                "metadataTargetCheckpointNs": checkpoint_fork.target_checkpoint_ns,
            }
        )
    if checkpoint_fork.target_checkpoint_ns != target_checkpoint_ns:
        return CheckpointReplayResolution(
            metadata={
                "status": "ignored",
                "reason": "fork_target_mismatch",
                "source": "checkpoint_fork",
                "requestedCheckpointId": requested_checkpoint_id,
                "targetThreadId": target_thread_id,
                "targetCheckpointNs": target_checkpoint_ns,
                "metadataTargetThreadId": checkpoint_fork.target_thread_id,
                "metadataTargetCheckpointNs": checkpoint_fork.target_checkpoint_ns,
            }
        )
    return CheckpointReplayResolution(
        checkpoint_id=requested_checkpoint_id,
        metadata={
            "status": "pending",
            "source": "checkpoint_fork",
            "requestedCheckpointId": requested_checkpoint_id,
            "targetThreadId": target_thread_id,
            "targetCheckpointNs": target_checkpoint_ns,
        },
    )


async def materialize_checkpoint_replay(
    checkpointer: object | None,
    *,
    tenant_id: str,
    checkpoint_fork: TrustedCheckpointFork | None,
    target_runtime: str,
    target_graph_profile: str | None,
    resolution: CheckpointReplayResolution,
    target_thread_id: str,
    target_checkpoint_ns: str,
) -> CheckpointReplayResolution:
    if resolution.checkpoint_id is None:
        return resolution
    if checkpoint_fork is None:
        return failed_checkpoint_replay_resolution(
            resolution,
            reason="invalid_fork_provenance",
        )
    if (
        checkpoint_fork.source_runtime != target_runtime
        or checkpoint_fork.source_graph_profile != target_graph_profile
    ):
        return failed_checkpoint_replay_resolution(
            resolution,
            reason="fork_execution_contract_mismatch",
        )
    try:
        fork = await materialize_checkpoint_fork(
            checkpointer,
            tenant_id=tenant_id,
            source_thread_id=checkpoint_fork.source_thread_id,
            source_checkpoint_ns=checkpoint_fork.source_checkpoint_ns,
            source_checkpoint_id=resolution.checkpoint_id,
            target_thread_id=target_thread_id,
            target_checkpoint_ns=target_checkpoint_ns,
        )
    except CheckpointForkError as error:
        return failed_checkpoint_replay_resolution(
            resolution,
            reason=error.reason,
        )
    return CheckpointReplayResolution(
        checkpoint_id=fork.checkpoint_id,
        metadata={
            **(resolution.metadata or {}),
            "status": "applied",
            "checkpointId": fork.checkpoint_id,
            "materialization": fork.mode,
        },
    )


def failed_checkpoint_replay_resolution(
    resolution: CheckpointReplayResolution,
    *,
    reason: str,
) -> CheckpointReplayResolution:
    return CheckpointReplayResolution(
        metadata={
            **(resolution.metadata or {}),
            "status": "failed",
            "reason": reason,
        },
        blocked=True,
    )


def run_metadata_with_defaults(
    metadata: Mapping[str, Any] | None,
    *,
    checkpoint_ns: str,
    streaming: bool = False,
    checkpoint_fork: TrustedCheckpointFork | None = None,
) -> dict[str, Any]:
    safe_metadata = {
        key: value
        for key, value in dict(metadata or {}).items()
        if key not in CHECKPOINT_PROVENANCE_METADATA_KEYS
    }
    run_metadata = {
        "runtime": "langgraph",
        "graph": "reactor_basic",
        **safe_metadata,
        "checkpoint_ns": checkpoint_ns,
    }
    if checkpoint_fork is not None:
        run_metadata.update(checkpoint_fork.metadata())
    if streaming:
        run_metadata["streaming"] = True
    return run_metadata


def stream_completion_payload(result: RunResult) -> dict[str, object]:
    payload: dict[str, object] = {
        "status": result.status,
        "nextActions": run_operator_next_actions(
            result.run_id,
            thread_id=result.thread_id,
            checkpoint_ns=result.checkpoint_ns,
        ),
    }
    if result.status != "completed":
        payload["response"] = result.response
    return payload


def run_operator_next_actions(
    run_id: str,
    *,
    thread_id: str | None = None,
    checkpoint_ns: str | None = None,
) -> list[dict[str, str]]:
    quoted_run_id = quote(run_id)
    metadata = {"sourceRunId": run_id}
    if thread_id is not None:
        metadata["threadId"] = thread_id
    if checkpoint_ns is not None:
        metadata["checkpointNs"] = checkpoint_ns
    return [
        {
            "id": "diagnose-run",
            "label": "Diagnose the run",
            **metadata,
            "command": f"reactor-runs diagnose {quoted_run_id} --output table",
        },
        {
            "id": "inspect-state-history",
            "label": "Inspect the run's LangGraph checkpoint state history",
            **metadata,
            "command": f"reactor-admin state-history {quoted_run_id} --output table",
        },
        {
            "id": "replay-stream",
            "label": "Replay the run's persisted stream events",
            **metadata,
            "command": f"reactor-runs replay {quoted_run_id} --output table",
        },
    ]


def token_usage_metadata(usage: TokenUsage | None) -> dict[str, object] | None:
    if usage is None:
        return None
    return {
        "inputTokens": usage.input_tokens,
        "outputTokens": usage.output_tokens,
        "totalTokens": usage.total_tokens,
        "maxOutputTokens": usage.max_output_tokens,
        "cachedTokens": usage.cached_tokens,
        "reasoningTokens": usage.reasoning_tokens,
    }


def stream_provider_usage(
    raw_event: Mapping[str, object],
    *,
    max_output_tokens: int,
) -> TokenUsage | None:
    data = raw_event.get("data")
    if isinstance(data, Mapping):
        typed_data = cast(Mapping[str, object], data)
        for key in ("output", "chunk"):
            usage = provider_usage_from_stream_value(
                typed_data.get(key),
                max_output_tokens=max_output_tokens,
            )
            if usage is not None:
                return usage
    params = raw_event.get("params")
    if isinstance(params, Mapping):
        typed_params = cast(Mapping[str, object], params)
        return provider_usage_from_stream_value(
            typed_params.get("data"),
            max_output_tokens=max_output_tokens,
        )
    return None


def native_graph_stream_result(
    raw_event: Mapping[str, object],
) -> Mapping[str, object] | None:
    if raw_event.get("event") != "on_chain_end":
        return None
    parent_ids = raw_event.get("parent_ids")
    if (
        not isinstance(parent_ids, Sequence)
        or isinstance(parent_ids, str | bytes | bytearray)
        or parent_ids
    ):
        return None
    data = raw_event.get("data")
    if not isinstance(data, Mapping):
        return None
    output = cast(Mapping[object, object], data).get("output")
    if not isinstance(output, Mapping):
        return None
    typed_output = cast(Mapping[object, object], output)
    if "response_text" not in typed_output and "response_metadata" not in typed_output:
        return None
    if not all(isinstance(key, str) for key in typed_output):
        return None
    return cast(Mapping[str, object], typed_output)


def provider_usage_from_stream_value(
    value: object,
    *,
    max_output_tokens: int,
) -> TokenUsage | None:
    usage = usage_from_provider_metadata(value, max_output_tokens=max_output_tokens)
    if usage is not None:
        return usage
    if isinstance(value, Mapping):
        typed_value = cast(Mapping[object, object], value)
        for nested in typed_value.values():
            usage = provider_usage_from_stream_value(
                nested,
                max_output_tokens=max_output_tokens,
            )
            if usage is not None:
                return usage
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        for nested in cast(Sequence[object], value):
            usage = provider_usage_from_stream_value(
                nested,
                max_output_tokens=max_output_tokens,
            )
            if usage is not None:
                return usage
    return None


def optional_metadata_json_object(value: object) -> dict[str, object] | None:
    if isinstance(value, Mapping):
        return string_keyed_mapping(cast(Mapping[Any, Any], value))
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return None
    if not isinstance(decoded, Mapping):
        return None
    return string_keyed_mapping(cast(Mapping[Any, Any], decoded))


def optional_metadata_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    typed_value = cast(list[object], value)
    return [item.strip() for item in typed_value if isinstance(item, str) and item.strip()]


def optional_metadata_middleware_policy(value: object):
    if not isinstance(value, Mapping):
        return None
    return langchain_middleware_policy_from_mapping(cast(Mapping[str, object], value))


def resolved_structured_output(metadata: Mapping[str, Any]) -> ResolvedStructuredOutput:
    response_format = optional_metadata_string(metadata.get("responseFormat"))
    ignored_format: dict[str, object] | None = None
    if response_format is not None and response_format.upper() not in ResponseFormat:
        ignored_format = {
            "status": "ignored",
            "reason": "invalid_response_format",
            "source": "metadata.responseFormat",
            "value": response_format,
        }
        response_format = None
    schema = optional_metadata_json_object(metadata.get("responseSchema"))
    schema_source = "metadata.responseSchema" if schema is not None else None
    ignored_schema: dict[str, object] | None = None
    if schema is not None:
        ignored_reason = ignored_response_schema_reason(schema)
        if ignored_reason is not None:
            schema = None
            schema_source = None
            ignored_schema = {
                "status": "ignored",
                "reason": ignored_reason,
                "source": "metadata.responseSchema",
            }
    elif "responseSchema" in metadata and schema is None:
        ignored_schema = {
            "status": "ignored",
            "reason": "invalid_response_schema",
            "source": "metadata.responseSchema",
        }
    return ResolvedStructuredOutput(
        response_format=response_format,
        schema=schema,
        schema_source=schema_source,
        ignored_schema=ignored_schema,
        ignored_format=ignored_format,
    )


def is_valid_json_schema(schema: Mapping[str, object]) -> bool:
    try:
        Draft202012Validator.check_schema(schema)
    except (SchemaError, UnknownType):
        return False
    return True


def ignored_response_schema_reason(schema: Mapping[str, object]) -> str | None:
    if not is_valid_json_schema(schema):
        return "invalid_response_schema"
    return None


def tool_profile_budget_metadata(budget: ToolProfileBudget) -> dict[str, object]:
    return {
        "maxTools": budget.max_tools,
        "allowedRiskLevels": sorted(budget.allowed_risk_levels)
        if budget.allowed_risk_levels is not None
        else None,
        "allowedTools": sorted(budget.allowed_tools) if budget.allowed_tools is not None else None,
        "deniedTools": sorted(budget.denied_tools),
    }


def tool_profile_budget_from_mapping(value: object) -> ToolProfileBudget | None:
    if not isinstance(value, Mapping):
        return None
    typed_value = cast(Mapping[str, object], value)
    if not set(typed_value).issubset(TOOL_PROFILE_BUDGET_FIELDS):
        return None
    try:
        budget = ToolProfileBudget(
            max_tools=optional_nonnegative_int(typed_value.get("maxTools")),
            allowed_risk_levels=optional_string_set(typed_value.get("allowedRiskLevels")),
            allowed_tools=optional_string_set(typed_value.get("allowedTools")),
            denied_tools=optional_string_set(typed_value.get("deniedTools")) or frozenset(),
        )
        budget.validate()
    except ValueError:
        return None
    return budget


def apply_tool_profile_budget(
    tools: Sequence[ToolSpec],
    budget: ToolProfileBudget,
) -> list[ToolSpec]:
    return apply_tool_profile_budget_with_evidence(tools, budget).tools


def apply_tool_profile_budget_with_evidence(
    tools: Sequence[ToolSpec],
    budget: ToolProfileBudget,
) -> ToolProfileBudgetApplication:
    filtered: list[ToolSpec] = []
    dropped_tools: list[Mapping[str, object]] = []
    for tool in tools:
        drop_reason = tool_profile_budget_drop_reason(tool, budget)
        if drop_reason is None:
            filtered.append(tool)
        else:
            dropped_tools.append(tool_profile_budget_drop(tool, drop_reason))
    if budget.max_tools is not None:
        for tool in filtered[budget.max_tools :]:
            dropped_tools.append(tool_profile_budget_drop(tool, "max_tools_exceeded"))
        filtered = filtered[: budget.max_tools]
    return ToolProfileBudgetApplication(
        tools=filtered,
        dropped_tools=tuple(dropped_tools),
    )


def blocked_research_plan_from_tool_exposure(
    metadata: Mapping[str, Any],
    tool_exposure: ToolExposure,
    *,
    message: str,
) -> dict[str, object] | None:
    if optional_metadata_string(metadata.get("graphProfile")) != "research":
        return None
    if tool_exposure.configured_tool_count <= 0:
        return None
    if RESEARCH_FORCED_TOOL in set(tool_exposure.active_tools):
        return None
    return {
        "status": "blocked",
        "profile": "research",
        "question": message,
        "reason": "forced_tool_unavailable",
        "missingTool": RESEARCH_FORCED_TOOL,
        "operatorAction": "allow_required_research_tool",
        "recoverySteps": [
            "remove_forced_tool_from_denied_tools",
            "allow_read_risk_tools_for_research_profile",
            "rerun_preflight_before_starting_research_run",
        ],
    }


def is_tool_allowed_by_profile_budget(tool: ToolSpec, budget: ToolProfileBudget) -> bool:
    return tool_profile_budget_drop_reason(tool, budget) is None


def tool_profile_budget_drop_reason(
    tool: ToolSpec,
    budget: ToolProfileBudget,
) -> str | None:
    if tool.qualified_name in budget.denied_tools:
        return "denied_tool"
    if budget.allowed_tools is not None and tool.qualified_name not in budget.allowed_tools:
        return "tool_not_allowed"
    if budget.allowed_risk_levels is not None and tool.risk_level not in budget.allowed_risk_levels:
        return "risk_level_not_allowed"
    return None


def tool_profile_budget_drop(tool: ToolSpec, reason: str) -> dict[str, object]:
    return {
        "tool": tool.qualified_name,
        "reason": reason,
        "riskLevel": tool.risk_level,
    }


def optional_nonnegative_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("boolean is not a valid integer")
    if isinstance(value, int) and value >= 0:
        return value
    raise ValueError("expected non-negative integer")


def optional_string_set(value: object) -> frozenset[str] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError("expected string list")
    values: set[str] = set()
    for item in cast(list[object], value):
        if not isinstance(item, str) or not item.strip():
            raise ValueError("expected non-empty string list")
        values.add(item.strip())
    return frozenset(values)


def integration_context_from_metadata(metadata: Mapping[str, Any]) -> dict[str, object] | None:
    allowed_keys = (
        "channel",
        "slackChannelId",
        "slack_channel_id",
        "slackThreadTs",
        "slack_thread_ts",
        "threadTs",
        "thread_ts",
        "teamId",
        "team_id",
    )
    context = {
        key: value
        for key in allowed_keys
        if (value := metadata.get(key)) is not None and is_integration_context_value(value)
    }
    return context or None


def is_integration_context_value(value: object) -> bool:
    return isinstance(value, str | int | float | bool)


def string_keyed_mapping(value: Mapping[Any, Any]) -> dict[str, object]:
    return {key: item for key, item in value.items() if isinstance(key, str)}


def run_once_graph_adapter() -> Any:
    from reactor.agents.runner import compiled_graph

    return compiled_graph()
