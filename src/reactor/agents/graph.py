from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import wraps
from typing import Any, Protocol, cast

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import StateGraph
from langgraph.types import interrupt

from reactor.agents.graph_boundary import JsonSafeReactorGraph
from reactor.agents.graph_composition import (
    GraphNodeSpec,
    GraphStageSpec,
    GraphSubgraphSpec,
    add_linear_subgraph_edges,
    add_subgraph_nodes,
    build_stage_subgraphs,
    graph_node_order,
    graph_stage_order,
)
from reactor.agents.interrupts import ApprovalResumePayload, approval_resume_from_raw
from reactor.agents.profiles import GraphProfile, GraphProfileRegistry
from reactor.agents.rag_grounding import (
    chunk_manifest_id,
    grounded_research_fallback_response,
    rag_tool_chunks,
    rag_tool_citation_content_hashes,
    rag_tool_citation_ids,
    rag_tool_source_labels,
)
from reactor.agents.state import (
    REACTOR_STATE_SCHEMA_VERSION,
    ReactorState,
    require_current_state_schema,
)
from reactor.agents.stores import GraphStore
from reactor.agents.tool_state import (
    PendingToolRequest,
    pending_tool_request_from_raw,
)
from reactor.context.assembler import assemble_model_prompt, integration_context_manifest
from reactor.guards.input import InputGuard, InputGuardBlocked
from reactor.guards.intents import IntentRegistry, RuleBasedIntentResolver
from reactor.guards.output import OutputGuard, OutputGuardBlocked
from reactor.hooks.runtime import ReactorHook, run_fail_open_hooks
from reactor.kernel.ids import new_id
from reactor.observability.tracing import trace_reactor_span
from reactor.persistence.tool_invocation_store import ToolInvocationClaim, ToolInvocationRecord
from reactor.prompts.profiles import PromptProfile, PromptRelease, resolve_tool_exposure
from reactor.providers.retry import is_transient_retry_exception
from reactor.response.boundary import OutputBoundaryEnforcer
from reactor.response.filters import ResponseFilterChain, ResponseFilterContext
from reactor.response.structured import (
    StructuredResponseRepairer,
    context_manifest_citation_ids,
    context_manifest_requires_citations,
    context_manifest_unsafe_citation_count,
    extract_response_format,
    merge_citation_response_schema,
)
from reactor.tools.execution import (
    ToolExecutionOutcome,
    ToolExecutionRequest,
    ToolExecutionResult,
    ToolHandler,
    ToolPolicy,
    ToolResultCache,
    admit_tool_execution,
    execute_tools_parallel,
    tool_invocation_record_from_outcome,
)
from reactor.tools.sanitizer import model_visible_tool_output, sanitize_tool_output

GRAPH_NODE_ORDER = (
    "guard",
    "context",
    "model",
    "approval_gate",
    "tool_executor",
    "output_guard",
    "hooks",
)

logger = logging.getLogger(__name__)

GRAPH_STAGE_ORDER = (
    "preflight",
    "generation",
    "tool_policy",
    "completion",
)


@dataclass(frozen=True)
class GraphProfileMetadata:
    graph_profile: str
    prompt_version: str
    model_provider: str
    selected_model: str
    checkpoint_ns: str
    temperature: float
    max_tool_calls: int
    active_tools: list[str]
    tool_choice: str | dict[str, str] | None = None
    tool_profile_budget: dict[str, object] | None = None


class ToolInvocationAuditStore(Protocol):
    async def claim(self, record: ToolInvocationRecord) -> ToolInvocationClaim: ...

    async def save(self, record: ToolInvocationRecord) -> ToolInvocationRecord: ...


@dataclass(frozen=True)
class ToolProfileBudgetApplication:
    active_tools: list[str]
    dropped_tools: list[dict[str, object]]


class LangChainChatModel(Protocol):
    async def ainvoke(self, input: object, config: object | None = None) -> object: ...


def append_node(state: ReactorState, node_name: str) -> list[str]:
    return [*state.get("node_sequence", []), node_name]


def graph_node_attributes(state: ReactorState, node_name: str) -> dict[str, object | None]:
    return {
        "reactor.graph.node": node_name,
        "reactor.run_id": state.get("run_id"),
        "reactor.tenant_id": state.get("tenant_id", "local"),
        "reactor.user_id": state.get("user_id", "anonymous"),
    }


async def guard_step(state: ReactorState) -> ReactorState:
    with trace_reactor_span("reactor.graph.guard", graph_node_attributes(state, "guard")):
        messages = state.get("messages", [])
        latest_user = next(
            (
                message.content
                for message in reversed(messages)
                if isinstance(message, HumanMessage)
            ),
            "",
        )
        InputGuard().check(str(latest_user))
        return {
            "guard_status": "allowed",
            "node_sequence": append_node(state, "guard"),
        }


def make_guard_step(input_guard: InputGuard):
    async def profiled_guard_step(state: ReactorState) -> ReactorState:
        with trace_reactor_span("reactor.graph.guard", graph_node_attributes(state, "guard")):
            messages = state.get("messages", [])
            latest_user = next(
                (
                    message.content
                    for message in reversed(messages)
                    if isinstance(message, HumanMessage)
                ),
                "",
            )
            await check_input_guard_for_state(input_guard, state, str(latest_user))
            return {
                "guard_status": "allowed",
                "node_sequence": append_node(state, "guard"),
            }

    return profiled_guard_step


def make_intent_aware_guard_step(
    input_guard: InputGuard,
    *,
    intent_registry: IntentRegistry | None,
):
    resolver = RuleBasedIntentResolver(intent_registry) if intent_registry is not None else None

    async def profiled_guard_step(state: ReactorState) -> ReactorState:
        with trace_reactor_span("reactor.graph.guard", graph_node_attributes(state, "guard")):
            messages = state.get("messages", [])
            latest_user = latest_human_message_content(messages)
            await check_input_guard_for_state(input_guard, state, str(latest_user))
            update: ReactorState = {
                "guard_status": "allowed",
                "node_sequence": append_node(state, "guard"),
            }
            if resolver is None:
                return update
            try:
                resolved = await resolver.resolve(str(latest_user))
            except Exception:
                return {
                    **update,
                    "response_metadata": {
                        **state.get("response_metadata", {}),
                        "intent_resolution_attempted": True,
                        "intent_resolution_status": "failed_open",
                    },
                }
            if resolved is None:
                return {
                    **update,
                    "response_metadata": {
                        **state.get("response_metadata", {}),
                        "intent_resolution_attempted": True,
                        "intent_resolution_status": "unmatched",
                    },
                }
            return {
                **update,
                "graph_profile": resolved.profile,
                "response_metadata": {
                    **state.get("response_metadata", {}),
                    "intent_resolution_attempted": True,
                    "intent_resolution_status": "matched",
                    "intent_name": resolved.intent_name,
                    "intent_confidence": resolved.confidence,
                    "intent_classified_by": resolved.classified_by,
                    "intent_latency_ms": resolved.latency_ms,
                    "intent_matched_keywords": list(resolved.matched_keywords),
                },
            }

    return profiled_guard_step


async def check_input_guard_for_state(
    input_guard: InputGuard,
    state: ReactorState,
    latest_user: str,
) -> None:
    tenant_id = state.get("tenant_id", "global")
    try:
        await input_guard.check_async(
            latest_user,
            tenant_id=tenant_id,
            user_id=state.get("user_id", "anonymous"),
        )
    except InputGuardBlocked as exc:
        raise InputGuardBlocked(
            exc.reason,
            metadata={
                **exc.as_metadata(),
                "run_id": state.get("run_id", ""),
                "tenant_id": tenant_id,
                "graph_node": "guard",
            },
        ) from exc


async def context_step(state: ReactorState) -> ReactorState:
    with trace_reactor_span("reactor.graph.context", graph_node_attributes(state, "context")):
        messages = state.get("messages", [])
        return {
            "context_manifest": {
                "message_count": len(messages),
                "tenant_id": state.get("tenant_id", "local"),
                "user_id": state.get("user_id", "anonymous"),
            },
            "node_sequence": append_node(state, "context"),
        }


def make_context_step(graph_profile: GraphProfile | None):
    async def profiled_context_step(state: ReactorState) -> ReactorState:
        with trace_reactor_span("reactor.graph.context", graph_node_attributes(state, "context")):
            messages = state.get("messages", [])
            profile_metadata = profile_metadata_from_state(state, graph_profile)
            latest_user = latest_human_message_content(messages)
            assembled_prompt = assemble_model_prompt(
                release=prompt_release_from_profile(profile_metadata),
                graph_profile_instructions=graph_profile_instructions(profile_metadata),
                request_system_prompt=optional_state_text(state, "request_system_prompt"),
                integration_context=state.get("integration_context"),
                active_tools=profile_metadata.active_tools,
                latest_user_request=latest_user,
                approval_state=state.get("approval_status", "not_required"),
                session_memory=state.get("session_memory"),
                rag_context=state.get("rag_context"),
                recent_messages=render_recent_messages(messages),
                tool_outputs=state.get("tool_results", []),
            )
            integration_manifest = integration_context_manifest(
                state.get("integration_context"),
                active_tools=profile_metadata.active_tools,
            )
            context_manifest: dict[str, object] = {
                "message_count": len(messages),
                "tenant_id": state.get("tenant_id", "local"),
                "user_id": state.get("user_id", "anonymous"),
                "graph_profile": profile_metadata.graph_profile,
                "state_schema_version": state.get(
                    "state_schema_version",
                    REACTOR_STATE_SCHEMA_VERSION,
                ),
                "checkpoint_ns": profile_metadata.checkpoint_ns,
                "prompt_version": profile_metadata.prompt_version,
                "prompt_template_version": assembled_prompt.prompt_template_version,
                "prompt_release_hash": assembled_prompt.prompt_release_hash,
                "rendered_prompt_checksum": assembled_prompt.rendered_prompt_checksum,
                "request_system_prompt": bool(optional_state_text(state, "request_system_prompt")),
                "sections": assembled_prompt.context_manifest["sections"],
            }
            if integration_manifest is not None:
                context_manifest["integration_context"] = integration_manifest
            if profile_metadata.tool_choice is not None:
                context_manifest["tool_choice"] = profile_metadata.tool_choice
            if profile_metadata.tool_profile_budget is not None:
                context_manifest["tool_profile_budget"] = profile_metadata.tool_profile_budget
            research_plan = research_plan_from_profile(
                profile_metadata,
                str(latest_user),
                tool_results=state.get("tool_results", []),
            )
            if research_plan is not None:
                context_manifest["research_plan"] = research_plan
            result: ReactorState = {
                "graph_profile": profile_metadata.graph_profile,
                "state_schema_version": state.get(
                    "state_schema_version",
                    REACTOR_STATE_SCHEMA_VERSION,
                ),
                "prompt_version": profile_metadata.prompt_version,
                "model_provider": profile_metadata.model_provider,
                "selected_model": profile_metadata.selected_model,
                "temperature": profile_metadata.temperature,
                "max_tool_calls": profile_metadata.max_tool_calls,
                "active_tools": profile_metadata.active_tools,
                "rendered_system_prompt": assembled_prompt.rendered_prompt,
                "context_manifest": context_manifest,
                "node_sequence": append_node(state, "context"),
            }
            if profile_metadata.tool_profile_budget is not None:
                result["tool_profile_budget_metadata"] = profile_metadata.tool_profile_budget
            if research_plan is not None:
                result["research_plan"] = research_plan
            return result

    return profiled_context_step


def make_profiled_context_step(
    graph_profile: GraphProfile | None,
    graph_profile_registry: GraphProfileRegistry | None,
):
    async def profiled_context_step(state: ReactorState) -> ReactorState:
        return await make_context_step(
            resolve_graph_profile_for_state(state, graph_profile, graph_profile_registry)
        )(state)

    return profiled_context_step


async def model_step(state: ReactorState) -> ReactorState:
    with trace_reactor_span("reactor.graph.model", graph_node_attributes(state, "model")):
        messages = state.get("messages", [])
        latest_user = next(
            (
                message.content
                for message in reversed(messages)
                if isinstance(message, HumanMessage)
            ),
            "",
        )
        max_tool_calls = state.get("max_tool_calls", 0)
        tool_call_count = state.get("tool_call_count", 0)
        if tool_call_count >= max_tool_calls:
            response_text = (
                "Tool budget is exhausted. Reactor is returning a final answer without "
                f"additional tool calls. Input: {latest_user}"
            )
            stop_reason = "max_tool_calls"
            active_tools: list[str] = []
        else:
            response_text = deterministic_fallback_response(latest_user)
            stop_reason = "completed"
            active_tools = state.get("active_tools", [])
        return {
            "response_text": response_text,
            "messages": [AIMessage(content=response_text)],
            "tool_call_count": state.get("tool_call_count", 0),
            "active_tools": active_tools,
            "response_metadata": {
                **state.get("response_metadata", {}),
                "stop_reason": stop_reason,
            },
            "node_sequence": append_node(state, "model"),
        }


def make_model_step(
    graph_profile: GraphProfile | None,
    *,
    chat_model: LangChainChatModel | None = None,
):
    async def profiled_model_step(state: ReactorState) -> ReactorState:
        with trace_reactor_span("reactor.graph.model", graph_node_attributes(state, "model")):
            messages = state.get("messages", [])
            latest_user = next(
                (
                    message.content
                    for message in reversed(messages)
                    if isinstance(message, HumanMessage)
                ),
                "",
            )
            profile_metadata = profile_metadata_from_state(state, graph_profile)
            max_tool_calls = profile_metadata.max_tool_calls
            tool_call_count = state.get("tool_call_count", 0)
            model_runtime: str | None = None
            model_error_type: str | None = None
            model_retry_count = 0
            active_tools: list[str]
            response_messages: list[AnyMessage]
            research_plan = state.get("research_plan")
            research_evidence_missing = is_research_evidence_missing(research_plan)
            if research_evidence_missing:
                response_text = research_evidence_missing_response(research_plan)
                stop_reason = "research_evidence_missing"
                active_tools = list(profile_metadata.active_tools)
                response_messages = [AIMessage(content=response_text)]
            elif tool_call_count >= max_tool_calls:
                response_text = (
                    "Tool budget is exhausted. Reactor is returning a final answer without "
                    f"additional tool calls. Input: {latest_user}"
                )
                stop_reason = "max_tool_calls"
                active_tools = []
                response_messages = [AIMessage(content=response_text)]
            else:
                if chat_model is not None:
                    try:
                        model_response, model_retry_count = await invoke_chat_model_with_retry(
                            chat_model,
                            state,
                            max_retries=1,
                        )
                        response_text = message_content_text(model_response)
                        response_messages = [model_response]
                        model_runtime = "langchain"
                    except Exception as exc:
                        response_text = deterministic_fallback_response(
                            latest_user,
                            research_plan=research_plan,
                            tool_results=state.get("tool_results", []),
                        )
                        response_messages = [AIMessage(content=response_text)]
                        model_runtime = "deterministic_fallback"
                        model_error_type = type(exc).__name__
                else:
                    response_text = deterministic_fallback_response(
                        latest_user,
                        research_plan=research_plan,
                        tool_results=state.get("tool_results", []),
                    )
                    response_messages = [AIMessage(content=response_text)]
                stop_reason = "completed"
                active_tools = list(profile_metadata.active_tools)
            response_metadata = {
                **state.get("response_metadata", {}),
                "graph_profile": profile_metadata.graph_profile,
                "state_schema_version": state.get(
                    "state_schema_version",
                    REACTOR_STATE_SCHEMA_VERSION,
                ),
                "prompt_version": profile_metadata.prompt_version,
                "model_provider": profile_metadata.model_provider,
                "selected_model": profile_metadata.selected_model,
                "checkpoint_ns": profile_metadata.checkpoint_ns,
                "temperature": profile_metadata.temperature,
                "stop_reason": stop_reason,
            }
            if tool_call_count < max_tool_calls and model_runtime is not None:
                response_metadata["model_runtime"] = model_runtime
                if model_retry_count:
                    response_metadata["model_retry_count"] = model_retry_count
                if model_runtime == "deterministic_fallback":
                    response_metadata["model_fallback_used"] = True
                    response_metadata["model_error_type"] = model_error_type
            if profile_metadata.tool_choice is not None:
                response_metadata["tool_choice"] = profile_metadata.tool_choice
            if profile_metadata.tool_profile_budget is not None:
                response_metadata["tool_profile_budget"] = profile_metadata.tool_profile_budget
            if isinstance(research_plan, Mapping):
                response_metadata["research_plan"] = research_plan_response_metadata(
                    cast(Mapping[str, object], research_plan)
                )
            return {
                "graph_profile": profile_metadata.graph_profile,
                "state_schema_version": state.get(
                    "state_schema_version",
                    REACTOR_STATE_SCHEMA_VERSION,
                ),
                "prompt_version": profile_metadata.prompt_version,
                "model_provider": profile_metadata.model_provider,
                "selected_model": profile_metadata.selected_model,
                "temperature": profile_metadata.temperature,
                "max_tool_calls": profile_metadata.max_tool_calls,
                "response_text": response_text,
                "messages": response_messages,
                "tool_call_count": state.get("tool_call_count", 0),
                "active_tools": active_tools,
                "response_metadata": response_metadata,
                "node_sequence": append_node(state, "model"),
            }

    return profiled_model_step


def make_profiled_model_step(
    graph_profile: GraphProfile | None,
    graph_profile_registry: GraphProfileRegistry | None,
    *,
    chat_model: LangChainChatModel | None = None,
):
    async def profiled_model_step(state: ReactorState) -> ReactorState:
        return await make_model_step(
            resolve_graph_profile_for_state(state, graph_profile, graph_profile_registry),
            chat_model=chat_model,
        )(state)

    return profiled_model_step


def make_approval_gate_step(
    *,
    use_interrupts: bool = False,
    tool_invocation_store: ToolInvocationAuditStore | None = None,
):
    async def approval_gate_step(state: ReactorState) -> ReactorState:
        with trace_reactor_span(
            "reactor.graph.approval_gate",
            graph_node_attributes(state, "approval_gate"),
        ):
            return await resolve_approval_gate(
                state,
                use_interrupts=use_interrupts,
                tool_invocation_store=tool_invocation_store,
            )

    return approval_gate_step


async def approval_gate_step(state: ReactorState) -> ReactorState:
    return await make_approval_gate_step()(state)


async def resolve_approval_gate(
    state: ReactorState,
    *,
    use_interrupts: bool,
    tool_invocation_store: ToolInvocationAuditStore | None = None,
) -> ReactorState:
    pending_tool = pending_tool_request_from_state(state)
    if pending_tool is None:
        return {
            "approval_status": "not_required",
            "response_metadata": {
                **state.get("response_metadata", {}),
                "approval_status": "not_required",
            },
            "node_sequence": append_node(state, "approval_gate"),
        }
    resume = approval_resume_from_state(state)
    if resume is not None and resume.approved is False:
        return {
            "approval_status": "rejected",
            "tool_results": [],
            "response_metadata": {
                **state.get("response_metadata", {}),
                "approval_status": "rejected",
                "approval_id": resume.approval_id,
                "approval_decided_by": resume.decided_by,
                "approval_reason": resume.reason,
                "stop_reason": "approval_rejected",
            },
            "node_sequence": append_node(state, "approval_gate"),
        }
    request = ToolExecutionRequest(
        run_id=state.get("run_id", ""),
        tenant_id=state.get("tenant_id", "local"),
        user_id=state.get("user_id", "anonymous"),
        tool=pending_tool.tool,
        input_payload=pending_tool.input_payload,
        trusted_user_groups=trusted_user_groups_from_state(state),
        approval_id=resume.approval_id if resume is not None else None,
    )
    policy = ToolPolicy(approved_approval_ids={resume.approval_id} if resume is not None else set())
    decision = admit_tool_execution(request, policy)
    if decision.requires_approval:
        approval_request = {
            "run_id": request.run_id,
            "tenant_id": request.tenant_id,
            "tool_id": request.tool.qualified_name,
            "tool_risk_level": request.tool.risk_level,
            "tool_timeout_ms": request.tool.timeout_ms,
            "requested_by": request.user_id,
            "input_payload": dict(request.input_payload),
            "idempotency_key": decision.idempotency_key,
        }
        await persist_pending_approval_tool_invocation_audit_record(
            request,
            tool_invocation_store=tool_invocation_store,
        )
        if use_interrupts:
            resume = approval_resume_from_raw(
                interrupt(
                    {
                        "approval_request": approval_request,
                        "approval_status": "pending",
                    }
                )
            )
            if resume.approved is False:
                return {
                    "approval_status": "rejected",
                    "tool_results": [],
                    "response_metadata": {
                        **state.get("response_metadata", {}),
                        "approval_status": "rejected",
                        "approval_id": resume.approval_id,
                        "approval_decided_by": resume.decided_by,
                        "approval_reason": resume.reason,
                        "stop_reason": "approval_rejected",
                    },
                    "node_sequence": append_node(state, "approval_gate"),
                }
            return {
                "approval_status": "approved",
                "response_metadata": {
                    **state.get("response_metadata", {}),
                    "approval_status": "approved",
                    "approval_id": resume.approval_id,
                    "approval_decided_by": resume.decided_by,
                },
                "node_sequence": append_node(state, "approval_gate"),
            }
        return {
            "approval_status": "pending",
            "tool_results": [],
            "response_metadata": {
                **state.get("response_metadata", {}),
                "approval_status": "pending",
                "approval_request": approval_request,
                "stop_reason": "approval_required",
            },
            "node_sequence": append_node(state, "approval_gate"),
        }
    return {
        "approval_status": "approved" if resume is not None else "not_required",
        "response_metadata": {
            **state.get("response_metadata", {}),
            "approval_status": "approved" if resume is not None else "not_required",
            "approval_id": decision.approval_id,
        },
        "node_sequence": append_node(state, "approval_gate"),
    }


def make_tool_executor_step(
    tool_result_cache: ToolResultCache | None,
    tool_handler: ToolHandler | None,
    tool_invocation_store: ToolInvocationAuditStore | None = None,
):
    async def tool_executor_step(state: ReactorState) -> ReactorState:
        with trace_reactor_span(
            "reactor.graph.tool_executor",
            graph_node_attributes(state, "tool_executor"),
        ):
            cache_statuses: list[str] = []
            tool_timeout_ms: int | None = None
            executed_tool_count = 0
            tool_results: list[dict[str, object]]
            tool_messages: list[AnyMessage]
            tool_output_guard_findings: list[str]
            if state.get("response_metadata", {}).get("stop_reason") == "max_tool_calls":
                tool_results = []
                tool_messages = []
                tool_output_guard_findings = []
            elif state.get("approval_status") in {"pending", "rejected"}:
                if state.get("approval_status") == "rejected":
                    await persist_rejected_approval_tool_invocation_audit_record(
                        state,
                        tool_invocation_store=tool_invocation_store,
                    )
                tool_results = []
                tool_messages = []
                tool_output_guard_findings = []
            elif (pending_tool := pending_tool_request_from_state(state)) is not None:
                approval_id = approval_id_from_state(state)
                request = ToolExecutionRequest(
                    run_id=state.get("run_id", ""),
                    tenant_id=state.get("tenant_id", "local"),
                    user_id=state.get("user_id", "anonymous"),
                    tool=pending_tool.tool,
                    input_payload=pending_tool.input_payload,
                    trusted_user_groups=trusted_user_groups_from_state(state),
                    approval_id=approval_id,
                )
                tool_timeout_ms = pending_tool.tool.timeout_ms
                actual_handler = tool_handler or default_tool_handler
                outcomes = await execute_tools_parallel(
                    [request],
                    actual_handler,
                    cache=tool_result_cache,
                    idempotency_store=tool_invocation_store,
                )
                cache_statuses = [
                    outcome.cache_status for outcome in outcomes if outcome.cache_status is not None
                ]
                executed_tool_count = sum(1 for outcome in outcomes if outcome.executed)
                tool_results = [
                    tool_result_payload(outcome.request, outcome.result) for outcome in outcomes
                ]
                tool_messages, tool_output_guard_findings = tool_messages_for_outcomes(outcomes)
            elif pending_tools := pending_tool_requests_from_state(state):
                actual_handler = tool_handler or default_tool_handler
                requests = [
                    ToolExecutionRequest(
                        run_id=state.get("run_id", ""),
                        tenant_id=state.get("tenant_id", "local"),
                        user_id=state.get("user_id", "anonymous"),
                        tool=pending_tool.tool,
                        input_payload=pending_tool.input_payload,
                        trusted_user_groups=trusted_user_groups_from_state(state),
                    )
                    for pending_tool in pending_tools
                ]
                outcomes = await execute_tools_parallel(
                    requests,
                    actual_handler,
                    cache=tool_result_cache,
                    idempotency_store=tool_invocation_store,
                )
                cache_statuses = [
                    outcome.cache_status for outcome in outcomes if outcome.cache_status is not None
                ]
                executed_tool_count = sum(1 for outcome in outcomes if outcome.executed)
                tool_timeout_ms = max(request.tool.timeout_ms for request in requests)
                tool_results = [
                    tool_result_payload(outcome.request, outcome.result) for outcome in outcomes
                ]
                tool_messages, tool_output_guard_findings = tool_messages_for_outcomes(outcomes)
            else:
                tool_results = state.get("tool_results", [])
                tool_messages = []
                tool_output_guard_findings = []
            response_metadata = dict(state.get("response_metadata", {}))
            if cache_statuses:
                response_metadata["tool_cache_status"] = (
                    cache_statuses[0] if len(set(cache_statuses)) == 1 else "mixed"
                )
            if tool_timeout_ms is not None:
                response_metadata["tool_timeout_ms"] = tool_timeout_ms
            if len(tool_results) > 1:
                response_metadata["parallel_tool_count"] = len(tool_results)
            if tool_output_guard_findings:
                response_metadata["tool_output_guard_findings"] = unique_in_order(
                    tool_output_guard_findings
                )
            return {
                "tool_results": tool_results,
                "messages": tool_messages,
                "tool_call_count": state.get("tool_call_count", 0) + executed_tool_count,
                "response_metadata": response_metadata,
                "node_sequence": append_node(state, "tool_executor"),
            }

    return tool_executor_step


async def tool_executor_step(state: ReactorState) -> ReactorState:
    return await make_tool_executor_step(None, None)(state)


async def persist_pending_approval_tool_invocation_audit_record(
    request: ToolExecutionRequest,
    *,
    tool_invocation_store: ToolInvocationAuditStore | None,
) -> None:
    if tool_invocation_store is None:
        return
    completed_at = datetime.now(UTC)
    result = ToolExecutionResult(
        status="started",
        payload={
            "approval_request": {
                "tool_id": request.tool.qualified_name,
                "tool_risk_level": request.tool.risk_level,
                "requested_by": request.user_id,
            },
            "error": {
                "code": "approval_required",
                "message": "tool execution is waiting for approval",
            },
        },
    )
    record = tool_invocation_record_from_outcome(
        ToolExecutionOutcome(
            request=request,
            result=result,
            cache_status=None,
            executed=False,
        ),
        invocation_id=new_id("tool_invocation"),
        started_at=completed_at,
        completed_at=None,
    )
    try:
        await tool_invocation_store.save(record)
    except Exception:
        raise RuntimeError("tool invocation audit persistence unavailable") from None


async def persist_rejected_approval_tool_invocation_audit_record(
    state: ReactorState,
    *,
    tool_invocation_store: ToolInvocationAuditStore | None,
) -> None:
    if tool_invocation_store is None:
        return
    pending_tool = pending_tool_request_from_state(state)
    resume = approval_resume_from_state(state)
    if pending_tool is None or resume is None or resume.approved is not False:
        return
    completed_at = datetime.now(UTC)
    request = ToolExecutionRequest(
        run_id=state.get("run_id", ""),
        tenant_id=state.get("tenant_id", "local"),
        user_id=state.get("user_id", "anonymous"),
        tool=pending_tool.tool,
        input_payload=pending_tool.input_payload,
        trusted_user_groups=trusted_user_groups_from_state(state),
        approval_id=resume.approval_id,
    )
    result = ToolExecutionResult.error(
        "approval_rejected",
        "tool execution rejected by approval decision",
    )
    payload = dict(result.payload)
    error = cast(dict[str, object], payload["error"])
    error["reason"] = resume.reason
    record = tool_invocation_record_from_outcome(
        ToolExecutionOutcome(
            request=request,
            result=ToolExecutionResult(status=result.status, payload=payload),
            cache_status=None,
            executed=False,
        ),
        invocation_id=new_id("tool_invocation"),
        started_at=completed_at,
        completed_at=completed_at,
    )
    try:
        await tool_invocation_store.save(record)
    except Exception:
        raise RuntimeError("tool invocation audit persistence unavailable") from None


async def default_tool_handler(request: ToolExecutionRequest) -> ToolExecutionResult:
    return ToolExecutionResult.success(
        {
            "tool_id": request.tool.qualified_name,
            "input_payload": dict(request.input_payload),
        }
    )


def tool_result_payload(
    request: ToolExecutionRequest,
    result: ToolExecutionResult,
) -> dict[str, object]:
    tool_call_id = tool_call_id_for_request(request)
    return {
        "approval_id": request.approval_id,
        "idempotency_key": request.idempotency_key,
        "status": result.status,
        "tool_call_id": tool_call_id,
        "tool_id": request.tool.qualified_name,
        "payload": dict(result.payload),
    }


def tool_messages_for_outcomes(
    outcomes: list[ToolExecutionOutcome],
) -> tuple[list[AnyMessage], list[str]]:
    messages: list[AnyMessage] = []
    findings: list[str] = []
    for outcome in outcomes:
        tool_call_id = tool_call_id_for_request(outcome.request)
        raw_content = json.dumps(
            {
                "status": outcome.result.status,
                "payload": model_visible_tool_output(outcome.result.payload),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        sanitized = sanitize_tool_output(raw_content)
        findings.extend(sanitized.findings)
        messages.extend(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": outcome.request.tool.qualified_name,
                            "args": dict(outcome.request.input_payload),
                            "id": tool_call_id,
                        }
                    ],
                ),
                ToolMessage(
                    content=sanitized.model_visible_text,
                    name=outcome.request.tool.qualified_name,
                    tool_call_id=tool_call_id,
                ),
            ]
        )
    return messages, findings


def unique_in_order(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def make_output_guard_step(output_guard: OutputGuard):
    async def output_guard_step(state: ReactorState) -> ReactorState:
        with trace_reactor_span(
            "reactor.graph.output_guard",
            graph_node_attributes(state, "output_guard"),
        ):
            original = state.get("response_text", "")
            tenant_id = state.get("tenant_id", "local")
            try:
                checked = await output_guard.check_async(
                    original,
                    tenant_id=tenant_id,
                )
            except OutputGuardBlocked as exc:
                raise OutputGuardBlocked(
                    exc.reason,
                    metadata={
                        **exc.as_metadata(),
                        "run_id": state.get("run_id", ""),
                        "tenant_id": tenant_id,
                        "graph_node": "output_guard",
                    },
                ) from exc
            status = "modified" if checked != original else "allowed"
            return {
                "response_text": checked,
                "output_guard_status": status,
                "response_metadata": {
                    **state.get("response_metadata", {}),
                    "output_guard_status": status,
                },
                "node_sequence": append_node(state, "output_guard"),
            }

    return output_guard_step


def make_response_filter_step(
    output_guard: OutputGuard,
    response_filter_chain: ResponseFilterChain | None,
    output_boundary_enforcer: OutputBoundaryEnforcer | None,
    structured_response_repairer: StructuredResponseRepairer | None,
):
    output_guard_step = make_output_guard_step(output_guard)

    async def response_filter_step(state: ReactorState) -> ReactorState:
        completion_state = research_completion_state(state)
        guarded = cast(
            ReactorState,
            {
                **completion_state,
                **await output_guard_step(completion_state),
            },
        )
        original = guarded.get("response_text", completion_state.get("response_text", ""))
        structured = original
        response_metadata = dict(
            guarded.get("response_metadata", completion_state.get("response_metadata", {}))
        )
        if structured_response_repairer is not None:
            response_format = extract_response_format(completion_state.get("response_format"))
            citation_ids = context_manifest_citation_ids(completion_state.get("context_manifest"))
            unsafe_citation_count = context_manifest_unsafe_citation_count(
                completion_state.get("context_manifest")
            )
            response_schema = merge_citation_response_schema(
                completion_state.get("response_schema"),
                completion_state.get("context_manifest"),
            )
            if (
                context_manifest_requires_citations(state.get("context_manifest"))
                and response_format.value == "JSON"
            ):
                response_metadata["structured_output_citation_policy"] = "required"
                response_metadata["structured_output_citation_count"] = len(citation_ids)
                response_metadata["structured_output_allowed_citation_ids"] = citation_ids
                if unsafe_citation_count:
                    blocked_response = "Response blocked by structured output policy."
                    response_metadata["structured_output_status"] = "invalid"
                    response_metadata["structured_output_error_code"] = (
                        "UNSAFE_CONTEXT_CITATION_IDS"
                    )
                    response_metadata["structured_output_unsafe_citation_count"] = (
                        unsafe_citation_count
                    )
                    response_metadata["stop_reason"] = "structured_output_invalid"
                    return {
                        **guarded,
                        "response_text": blocked_response,
                        "messages": [AIMessage(content=blocked_response)],
                        "response_metadata": response_metadata,
                    }
                if not citation_ids:
                    blocked_response = "Response blocked by structured output policy."
                    response_metadata["structured_output_status"] = "invalid"
                    response_metadata["structured_output_error_code"] = "MISSING_CONTEXT_CITATIONS"
                    response_metadata["stop_reason"] = "structured_output_invalid"
                    return {
                        **guarded,
                        "response_text": blocked_response,
                        "messages": [AIMessage(content=blocked_response)],
                        "response_metadata": response_metadata,
                    }
            structured_result = await structured_response_repairer.validate_and_repair(
                structured,
                response_format,
                schema=response_schema,
            )
            if structured_result.success and structured_result.content is not None:
                structured = structured_result.content
                response_metadata["structured_output_status"] = (
                    "valid" if structured == original else "repaired"
                )
            elif response_format.value != "TEXT":
                blocked_response = "Response blocked by structured output policy."
                response_metadata["structured_output_status"] = "invalid"
                response_metadata["structured_output_error_code"] = (
                    structured_result.error_code or "INVALID_RESPONSE"
                )
                response_metadata["stop_reason"] = "structured_output_invalid"
                return {
                    **guarded,
                    "response_text": blocked_response,
                    "messages": [AIMessage(content=blocked_response)],
                    "response_metadata": response_metadata,
                }
        filtered = structured
        if response_filter_chain is not None and response_filter_chain.size > 0:
            filtered = await response_filter_chain.apply(
                structured,
                ResponseFilterContext(
                    tenant_id=state.get("tenant_id", "local"),
                    user_id=state.get("user_id", "anonymous"),
                    tools_used=[str(tool) for tool in state.get("active_tools", [])],
                    duration_ms=0,
                    tool_insights=render_tool_outputs(state.get("tool_results", [])),
                ),
            )
            response_metadata["response_filter_status"] = (
                "modified" if filtered != structured else "unchanged"
            )
        bounded = filtered
        if output_boundary_enforcer is not None:
            boundary_retry_metadata: dict[str, object] = {}
            boundary_result = await output_boundary_enforcer.enforce(
                filtered,
                metadata={
                    "run_id": state.get("run_id"),
                    "tenant_id": state.get("tenant_id", "local"),
                    "user_id": state.get("user_id", "anonymous"),
                },
                attempt_longer_response=lambda content, required_min: (
                    output_boundary_retry_once_response(
                        state,
                        content,
                        required_min,
                        retry_metadata=boundary_retry_metadata,
                    )
                ),
            )
            if boundary_result is None:
                blocked_response = "Response blocked by output boundary policy."
                return {
                    **guarded,
                    "response_text": blocked_response,
                    "messages": [AIMessage(content=blocked_response)],
                    "response_metadata": {
                        **response_metadata,
                        "output_boundary_status": "failed",
                        "stop_reason": "output_boundary_failed",
                    },
                }
            bounded = boundary_result
            response_metadata["output_boundary_status"] = (
                "modified" if bounded != filtered else "unchanged"
            )
            response_metadata.update(boundary_retry_metadata)
        if bounded == original:
            return {
                **guarded,
                "response_metadata": response_metadata,
            }
        return {
            **guarded,
            "response_text": bounded,
            "messages": [AIMessage(content=bounded)],
            "response_metadata": response_metadata,
        }

    return response_filter_step


def output_boundary_retry_once_response(
    state: ReactorState,
    content: str,
    required_min: int,
    *,
    retry_metadata: dict[str, object],
) -> str:
    latest_user = latest_human_content(state.get("messages", []))
    detail = (
        "Additional detail: The response was expanded once to satisfy the configured "
        "minimum output boundary while preserving the original answer and request "
        f"context. Request summary: {latest_user or 'not provided'}."
    )
    expanded = f"{content}\n\n{detail}"
    while len(expanded) < required_min:
        expanded = f"{expanded} Additional detail."
    retry_metadata["output_boundary_retry"] = "used"
    return expanded


def latest_human_content(messages: Sequence[AnyMessage]) -> str:
    return str(
        next(
            (
                message_content_text(message.content)
                for message in reversed(messages)
                if isinstance(message, HumanMessage)
            ),
            "",
        )
    )


async def output_guard_step(state: ReactorState) -> ReactorState:
    return await make_output_guard_step(OutputGuard())(state)


def make_hooks_step(after_complete_hooks: Sequence[ReactorHook]):
    async def hooks_step(state: ReactorState) -> ReactorState:
        with trace_reactor_span("reactor.graph.hooks", graph_node_attributes(state, "hooks")):
            failures = await run_fail_open_hooks(after_complete_hooks, state)
            response_metadata: dict[str, object] = {
                **state.get("response_metadata", {}),
                "hooks_status": "completed_with_failures" if failures else "completed",
            }
            if failures:
                response_metadata["hook_failures"] = [failure.as_metadata() for failure in failures]
            return {
                "response_metadata": response_metadata,
                "node_sequence": append_node(state, "hooks"),
            }

    return hooks_step


async def hooks_step(state: ReactorState) -> ReactorState:
    return await make_hooks_step(())(state)


def build_reactor_graph(
    checkpointer: BaseCheckpointSaver[Any] | bool | None = None,
    graph_store: GraphStore | None = None,
    input_guard: InputGuard | None = None,
    output_guard: OutputGuard | None = None,
    response_filter_chain: ResponseFilterChain | None = None,
    output_boundary_enforcer: OutputBoundaryEnforcer | None = None,
    structured_response_repairer: StructuredResponseRepairer | None = None,
    graph_profile: GraphProfile | None = None,
    graph_profile_registry: GraphProfileRegistry | None = None,
    intent_registry: IntentRegistry | None = None,
    tool_result_cache: ToolResultCache | None = None,
    tool_handler: ToolHandler | None = None,
    tool_invocation_store: ToolInvocationAuditStore | None = None,
    chat_model: LangChainChatModel | None = None,
    use_interrupts: bool = False,
    after_complete_hooks: Sequence[ReactorHook] = (),
):
    graph = StateGraph(ReactorState)
    stages = build_reactor_graph_stages(
        input_guard=input_guard,
        output_guard=output_guard,
        response_filter_chain=response_filter_chain,
        output_boundary_enforcer=output_boundary_enforcer,
        structured_response_repairer=structured_response_repairer,
        graph_profile=graph_profile,
        graph_profile_registry=graph_profile_registry,
        intent_registry=intent_registry,
        tool_result_cache=tool_result_cache,
        tool_handler=tool_handler,
        tool_invocation_store=tool_invocation_store,
        chat_model=chat_model,
        use_interrupts=use_interrupts,
        after_complete_hooks=after_complete_hooks,
    )
    subgraphs = build_reactor_graph_subgraphs(stages)
    add_subgraph_nodes(graph, subgraphs)
    add_linear_subgraph_edges(graph, subgraphs)
    return JsonSafeReactorGraph(graph.compile(checkpointer=checkpointer, store=graph_store))


def build_reactor_graph_subgraphs(
    stages: Sequence[GraphStageSpec],
) -> tuple[GraphSubgraphSpec, ...]:
    return build_stage_subgraphs(stages, ReactorState)


def build_reactor_graph_stages(
    *,
    input_guard: InputGuard | None = None,
    output_guard: OutputGuard | None = None,
    response_filter_chain: ResponseFilterChain | None = None,
    output_boundary_enforcer: OutputBoundaryEnforcer | None = None,
    structured_response_repairer: StructuredResponseRepairer | None = None,
    graph_profile: GraphProfile | None = None,
    graph_profile_registry: GraphProfileRegistry | None = None,
    intent_registry: IntentRegistry | None = None,
    tool_result_cache: ToolResultCache | None = None,
    tool_handler: ToolHandler | None = None,
    tool_invocation_store: ToolInvocationAuditStore | None = None,
    chat_model: LangChainChatModel | None = None,
    use_interrupts: bool = False,
    after_complete_hooks: Sequence[ReactorHook] = (),
) -> tuple[GraphStageSpec, ...]:
    stages: tuple[GraphStageSpec, ...] = (
        GraphStageSpec(
            "preflight",
            (
                GraphNodeSpec(
                    "guard",
                    make_intent_aware_guard_step(
                        input_guard or InputGuard(),
                        intent_registry=intent_registry,
                    ),
                ),
                GraphNodeSpec(
                    "context",
                    make_profiled_context_step(graph_profile, graph_profile_registry),
                ),
            ),
        ),
        GraphStageSpec(
            "generation",
            (
                GraphNodeSpec(
                    "model",
                    make_profiled_model_step(
                        graph_profile,
                        graph_profile_registry,
                        chat_model=chat_model,
                    ),
                ),
            ),
        ),
        GraphStageSpec(
            "tool_policy",
            (
                GraphNodeSpec(
                    "approval_gate",
                    make_approval_gate_step(
                        use_interrupts=use_interrupts,
                        tool_invocation_store=tool_invocation_store,
                    ),
                ),
                GraphNodeSpec(
                    "tool_executor",
                    make_tool_executor_step(
                        tool_result_cache,
                        tool_handler,
                        tool_invocation_store,
                    ),
                ),
            ),
        ),
        GraphStageSpec(
            "completion",
            (
                GraphNodeSpec(
                    "output_guard",
                    make_response_filter_step(
                        output_guard or OutputGuard(),
                        response_filter_chain,
                        output_boundary_enforcer,
                        structured_response_repairer,
                    ),
                ),
                GraphNodeSpec("hooks", make_hooks_step(after_complete_hooks)),
            ),
        ),
    )
    stages = tuple(
        GraphStageSpec(
            stage.name,
            tuple(
                GraphNodeSpec(node.name, state_schema_guarded_action(node.action))
                for node in stage.nodes
            ),
        )
        for stage in stages
    )
    if graph_stage_order(stages) != GRAPH_STAGE_ORDER:
        raise ValueError("reactor graph stage order drifted")
    if graph_node_order(stages) != GRAPH_NODE_ORDER:
        raise ValueError("reactor graph node order drifted")
    return stages


def state_schema_guarded_action(action: Any) -> Any:
    @wraps(action)
    async def guarded(state: ReactorState) -> ReactorState:
        require_current_state_schema(state)
        return await action(state)

    return guarded


def resolve_graph_profile_for_state(
    state: ReactorState,
    graph_profile: GraphProfile | None,
    graph_profile_registry: GraphProfileRegistry | None,
) -> GraphProfile | None:
    profile_id = state.get("graph_profile")
    if not profile_id or graph_profile_registry is None:
        return graph_profile
    try:
        return graph_profile_registry.get(profile_id)
    except ValueError:
        return graph_profile


def profile_metadata_from_state(
    state: ReactorState,
    graph_profile: GraphProfile | None,
) -> GraphProfileMetadata:
    profile = graph_profile
    if profile is not None:
        profile.validate()
    tool_exposure = resolve_tool_exposure(
        profile_tools=list(profile.tool_allowlist) if profile is not None else [],
        request_tools=state.get("active_tools") if "active_tools" in state else None,
        policy=profile.tool_forcing_policy if profile is not None else None,
    )
    active_tools = list(tool_exposure.active_tools)
    tool_choice = tool_exposure.tool_choice
    existing_tool_profile_budget = state.get("tool_profile_budget_metadata")
    tool_profile_budget: dict[str, object] | None
    if isinstance(existing_tool_profile_budget, Mapping):
        tool_profile_budget = dict(cast(Mapping[str, object], existing_tool_profile_budget))
    else:
        tool_profile_budget = state_tool_profile_budget_metadata(state, active_tools)
    if tool_profile_budget is not None and not isinstance(existing_tool_profile_budget, Mapping):
        budget = state.get("tool_profile_budget", {})
        invalid_budget_reason = invalid_state_tool_profile_budget_reason(budget)
        if invalid_budget_reason is None:
            budget_application = state_tool_profile_budget_application(
                active_tools,
                state.get("active_tool_specs", []),
                budget,
            )
            active_tools = budget_application.active_tools
            tool_choice = tool_choice_allowed_by_active_tools(tool_choice, active_tools)
            if budget_application.dropped_tools:
                tool_profile_budget["dropped_tools"] = budget_application.dropped_tools
        else:
            tool_profile_budget["ignored_budget"] = {
                "status": "ignored",
                "reason": invalid_budget_reason,
                "source": "state",
            }
        tool_profile_budget = {
            **tool_profile_budget,
            "active_tool_count": len(active_tools),
        }
    return GraphProfileMetadata(
        graph_profile=state.get(
            "graph_profile",
            profile.profile_id if profile is not None else "standard",
        ),
        prompt_version=state.get(
            "prompt_version",
            profile.prompt_version if profile is not None else "standard-v1",
        ),
        model_provider=state.get(
            "model_provider",
            profile.model_provider if profile is not None else "openai",
        ),
        selected_model=state.get(
            "selected_model",
            profile.model if profile is not None else "gpt-5-mini",
        ),
        checkpoint_ns=state.get(
            "profile_checkpoint_ns",
            profile.checkpoint_ns if profile is not None else "reactor",
        ),
        temperature=state.get(
            "temperature",
            profile.temperature if profile is not None else 1.0,
        ),
        max_tool_calls=state.get(
            "max_tool_calls",
            profile.max_tool_calls if profile is not None else 0,
        ),
        active_tools=active_tools,
        tool_choice=tool_choice,
        tool_profile_budget=tool_profile_budget,
    )


def state_tool_profile_budget_metadata(
    state: ReactorState,
    active_tools: Sequence[str],
) -> dict[str, object] | None:
    budget = state.get("tool_profile_budget")
    if not isinstance(budget, Mapping):
        return None
    if not active_tools:
        return None
    return {"source": "state"}


def apply_state_tool_profile_budget(
    active_tools: Sequence[str],
    active_tool_specs: object,
    budget: object,
) -> list[str]:
    return state_tool_profile_budget_application(
        active_tools,
        active_tool_specs,
        budget,
    ).active_tools


def state_tool_profile_budget_application(
    active_tools: Sequence[str],
    active_tool_specs: object,
    budget: object,
) -> ToolProfileBudgetApplication:
    if not isinstance(budget, Mapping):
        return ToolProfileBudgetApplication(active_tools=list(active_tools), dropped_tools=[])
    typed_budget = cast(Mapping[str, object], budget)
    max_tools = optional_nonnegative_int(typed_budget.get("maxTools"))
    allowed_risk_levels = optional_string_set(typed_budget.get("allowedRiskLevels"))
    allowed_tools = optional_string_set(typed_budget.get("allowedTools"))
    denied_tools = optional_string_set(typed_budget.get("deniedTools")) or frozenset()
    risk_by_tool = state_tool_risk_by_name(active_tool_specs)
    filtered: list[str] = []
    dropped_tools: list[dict[str, object]] = []
    for tool_name in active_tools:
        risk_level = risk_by_tool.get(tool_name)
        if tool_name in denied_tools:
            dropped_tools.append(tool_profile_budget_drop(tool_name, "denied_tool", risk_level))
            continue
        if allowed_tools is not None and tool_name not in allowed_tools:
            dropped_tools.append(
                tool_profile_budget_drop(tool_name, "tool_not_allowed", risk_level)
            )
            continue
        if allowed_risk_levels is not None and risk_level not in allowed_risk_levels:
            dropped_tools.append(
                tool_profile_budget_drop(tool_name, "risk_level_not_allowed", risk_level)
            )
            continue
        filtered.append(tool_name)
    if max_tools is not None:
        for tool_name in filtered[max_tools:]:
            dropped_tools.append(
                tool_profile_budget_drop(
                    tool_name,
                    "max_tools_exceeded",
                    risk_by_tool.get(tool_name),
                )
            )
        filtered = filtered[:max_tools]
    return ToolProfileBudgetApplication(active_tools=filtered, dropped_tools=dropped_tools)


def invalid_state_tool_profile_budget_reason(budget: object) -> str | None:
    if not isinstance(budget, Mapping):
        return "invalid_state_budget"
    typed_budget = cast(Mapping[str, object], budget)
    if not is_optional_nonnegative_int(typed_budget.get("maxTools")):
        return "invalid_state_budget"
    for key in ("allowedRiskLevels", "allowedTools", "deniedTools"):
        if not is_optional_string_list(typed_budget.get(key)):
            return "invalid_state_budget"
    return None


def tool_profile_budget_drop(
    tool_name: str,
    reason: str,
    risk_level: str | None,
) -> dict[str, object]:
    detail: dict[str, object] = {
        "tool": tool_name,
        "reason": reason,
    }
    if risk_level is not None:
        detail["risk_level"] = risk_level
    return detail


def state_tool_risk_by_name(active_tool_specs: object) -> dict[str, str]:
    if not isinstance(active_tool_specs, Sequence) or isinstance(active_tool_specs, str | bytes):
        return {}
    risk_by_tool: dict[str, str] = {}
    for spec in cast(Sequence[object], active_tool_specs):
        if not isinstance(spec, Mapping):
            continue
        typed_spec = cast(Mapping[str, object], spec)
        qualified_name = optional_string(typed_spec.get("qualified_name")) or qualified_tool_name(
            typed_spec
        )
        risk_level = optional_string(typed_spec.get("risk_level"))
        if qualified_name is not None and risk_level is not None:
            risk_by_tool[qualified_name] = risk_level
    return risk_by_tool


def qualified_tool_name(spec: Mapping[str, object]) -> str | None:
    namespace = optional_string(spec.get("namespace"))
    name = optional_string(spec.get("name"))
    if namespace is None or name is None:
        return None
    return f"{namespace}:{name}"


def tool_choice_allowed_by_active_tools(
    tool_choice: str | dict[str, str] | None,
    active_tools: Sequence[str],
) -> str | dict[str, str] | None:
    if tool_choice is None:
        return None
    tool_name = tool_choice if isinstance(tool_choice, str) else tool_choice.get("name")
    if tool_name in set(active_tools):
        return tool_choice
    return None


def optional_nonnegative_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    return None


def is_optional_nonnegative_int(value: object) -> bool:
    return value is None or (not isinstance(value, bool) and isinstance(value, int) and value >= 0)


def optional_string_set(value: object) -> frozenset[str] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        return None
    values = frozenset(
        item.strip() for item in cast(list[object], value) if isinstance(item, str) and item.strip()
    )
    return values


def is_optional_string_list(value: object) -> bool:
    if value is None:
        return True
    if not isinstance(value, list):
        return False
    return all(isinstance(item, str) and bool(item.strip()) for item in cast(list[object], value))


def optional_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def latest_human_message_content(messages: list[AnyMessage]) -> str:
    return next(
        (
            str(message.content)
            for message in reversed(messages)
            if isinstance(message, HumanMessage)
        ),
        "",
    )


def optional_state_text(state: ReactorState, key: str) -> str | None:
    value = state.get(key)
    if not isinstance(value, str):
        return None
    clean_value = value.strip()
    return clean_value or None


def render_recent_messages(messages: list[AnyMessage]) -> list[str]:
    return [f"{message.type}: {message.content}" for message in messages]


def render_tool_outputs(tool_results: list[dict[str, object]]) -> list[str]:
    return [
        sanitize_tool_output(
            json.dumps(
                model_visible_tool_output(result),
                sort_keys=True,
                separators=(",", ":"),
            ),
        ).model_visible_text
        for result in tool_results
    ]


def research_plan_from_profile(
    profile_metadata: GraphProfileMetadata,
    latest_user_request: str,
    *,
    tool_results: Sequence[object] = (),
    execution_complete: bool = False,
) -> dict[str, object] | None:
    if profile_metadata.graph_profile != "research":
        return None
    plan: dict[str, object] = {
        "status": "planned",
        "profile": "research",
        "question": latest_user_request,
        "executionProfile": research_execution_profile_metadata(profile_metadata),
        "requiredEvidence": ["rag_citations", "source_labels"],
        "verificationSteps": [
            "retrieve_authorized_sources",
            "answer_with_citations",
            "check_uncited_claims",
        ],
    }
    citation_ids = rag_tool_citation_ids(tool_results)
    source_labels = rag_tool_source_labels(tool_results)
    retrieval_summary = research_retrieval_summary(tool_results, citation_count=len(citation_ids))
    if citation_ids and source_labels:
        plan["evidenceStatus"] = "grounded"
        plan["citationCount"] = len(citation_ids)
        plan["citationIds"] = citation_ids
        plan["sourceLabels"] = source_labels
        plan["sourceCount"] = len(source_labels)
        plan["answerContract"] = research_answer_contract(
            citation_ids=citation_ids,
            source_labels=source_labels,
        )
        plan["answerExtraction"] = research_answer_extraction_summary(
            tool_results,
            citation_ids,
        )
        plan["retrievalSummary"] = retrieval_summary
    elif citation_ids:
        plan["evidenceStatus"] = "missing"
        plan["missingEvidence"] = ["source_labels"]
        plan["citationCount"] = len(citation_ids)
        plan["citationIds"] = citation_ids
        plan["sourceCount"] = 0
        plan["retrievalSummary"] = retrieval_summary
        plan["operatorAction"] = "retry_with_source_labeled_rag"
        plan["recoverySteps"] = [
            "verify_rag_citations_include_source_uri",
            "rerun_research_profile_after_source_metadata_fix",
            "escalate_if_authorized_source_labels_are_unavailable",
        ]
    elif has_rag_tool_result(tool_results):
        plan["evidenceStatus"] = "missing"
        plan["missingEvidence"] = ["rag_citations"]
        plan["citationCount"] = 0
        plan["retrievalSummary"] = retrieval_summary
        plan["operatorAction"] = "retry_with_grounded_rag"
        plan["recoverySteps"] = [
            "verify_rag_tool_returned_citations",
            "rerun_research_profile_after_ingestion_or_acl_fix",
            "escalate_if_authorized_sources_are_unavailable",
        ]
    elif execution_complete:
        plan["evidenceStatus"] = "missing"
        plan["missingEvidence"] = ["rag_tool_execution"]
        plan["citationCount"] = 0
        plan["sourceCount"] = 0
        plan["retrievalSummary"] = retrieval_summary
        plan["operatorAction"] = "retry_required_rag_tool"
        plan["recoverySteps"] = [
            "verify_forced_rag_tool_call_was_emitted",
            "verify_rag_tool_handler_is_configured",
            "rerun_research_profile_after_tool_execution_fix",
        ]
    return plan


def research_completion_state(state: ReactorState) -> ReactorState:
    existing_plan = state.get("research_plan")
    if not isinstance(existing_plan, Mapping):
        return state
    profile_metadata = profile_metadata_from_state(state, None)
    completed_plan = research_plan_from_profile(
        profile_metadata,
        latest_human_message_content(state.get("messages", [])),
        tool_results=state.get("tool_results", []),
        execution_complete=True,
    )
    if completed_plan is None:
        return state
    existing_execution_profile = existing_plan.get("executionProfile")
    if isinstance(existing_execution_profile, Mapping):
        completed_plan["executionProfile"] = dict(
            cast(Mapping[str, object], existing_execution_profile)
        )
    context_manifest = dict(state.get("context_manifest", {}))
    context_manifest["research_plan"] = completed_plan
    response_metadata = dict(state.get("response_metadata", {}))
    response_metadata["research_plan"] = research_plan_response_metadata(completed_plan)
    evidence_status = completed_plan.get("evidenceStatus")
    if evidence_status == "grounded":
        response_text = (
            grounded_research_fallback_response(
                latest_human_message_content(state.get("messages", [])),
                completed_plan,
                tool_results=state.get("tool_results", []),
            )
            or "Response blocked by research evidence policy."
        )
        stop_reason = "completed"
    else:
        response_text = research_evidence_missing_response(completed_plan)
        stop_reason = "research_evidence_missing"
    response_metadata["stop_reason"] = stop_reason
    return {
        **state,
        "research_plan": completed_plan,
        "context_manifest": context_manifest,
        "response_text": response_text,
        "messages": [AIMessage(content=response_text)],
        "response_metadata": response_metadata,
    }


def research_plan_response_metadata(plan: Mapping[str, object]) -> dict[str, object]:
    metadata: dict[str, object] = {
        "status": str(plan.get("status") or "planned"),
        "requiredEvidence": string_list_from_mapping(plan, "requiredEvidence"),
        "verificationSteps": string_list_from_mapping(plan, "verificationSteps"),
    }
    execution_profile = mapping_from_mapping(plan, "executionProfile")
    if execution_profile:
        metadata["executionProfile"] = execution_profile
    evidence_status = plan.get("evidenceStatus")
    if isinstance(evidence_status, str) and evidence_status.strip():
        metadata["evidenceStatus"] = evidence_status.strip()
        metadata["citationCount"] = nonnegative_int_from_mapping(plan, "citationCount")
        metadata["citationIds"] = string_list_from_mapping(plan, "citationIds")
        source_labels = string_list_from_mapping(plan, "sourceLabels")
        if source_labels:
            metadata["sourceLabels"] = source_labels
        if "sourceCount" in plan:
            metadata["sourceCount"] = nonnegative_int_from_mapping(plan, "sourceCount")
        answer_contract = mapping_from_mapping(plan, "answerContract")
        if answer_contract:
            metadata["answerContract"] = answer_contract
        answer_extraction = mapping_from_mapping(plan, "answerExtraction")
        if answer_extraction:
            metadata["answerExtraction"] = answer_extraction
        missing_evidence = string_list_from_mapping(plan, "missingEvidence")
        if missing_evidence:
            metadata["missingEvidence"] = missing_evidence
        operator_action = plan.get("operatorAction")
        if isinstance(operator_action, str) and operator_action.strip():
            metadata["operatorAction"] = operator_action.strip()
        recovery_steps = string_list_from_mapping(plan, "recoverySteps")
        if recovery_steps:
            metadata["recoverySteps"] = recovery_steps
        retrieval_summary = mapping_from_mapping(plan, "retrievalSummary")
        if retrieval_summary:
            metadata["retrievalSummary"] = retrieval_summary
    return metadata


def is_research_evidence_missing(plan: object) -> bool:
    if not isinstance(plan, Mapping):
        return False
    plan_mapping = cast(Mapping[str, object], plan)
    evidence_status = plan_mapping.get("evidenceStatus")
    return isinstance(evidence_status, str) and evidence_status == "missing"


def research_evidence_missing_response(plan: object) -> str:
    missing_evidence: list[str] = []
    if isinstance(plan, Mapping):
        missing_evidence = string_list_from_mapping(
            cast(Mapping[str, object], plan),
            "missingEvidence",
        )
    if missing_evidence == ["source_labels"]:
        return (
            "Research evidence is missing required source labels. Reactor cannot complete "
            "this research answer until cited RAG sources include source labels."
        )
    return (
        "Research evidence is missing required citations. Reactor cannot complete "
        "this research answer until grounded RAG citations are available."
    )


def string_list_from_mapping(value: Mapping[str, object], key: str) -> list[str]:
    items = value.get(key)
    if not isinstance(items, list):
        return []
    return [item for item in cast(list[object], items) if isinstance(item, str)]


def nonnegative_int_from_mapping(value: Mapping[str, object], key: str) -> int:
    raw = value.get(key)
    if isinstance(raw, int) and raw >= 0:
        return raw
    return 0


def mapping_from_mapping(value: Mapping[str, object], key: str) -> dict[str, object]:
    raw = value.get(key)
    if not isinstance(raw, Mapping):
        return {}
    return dict(cast(Mapping[str, object], raw))


def research_execution_profile_metadata(
    profile_metadata: GraphProfileMetadata,
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "promptVersion": profile_metadata.prompt_version,
        "modelProvider": profile_metadata.model_provider,
        "model": profile_metadata.selected_model,
        "checkpointNs": profile_metadata.checkpoint_ns,
        "temperature": profile_metadata.temperature,
        "maxToolCalls": profile_metadata.max_tool_calls,
        "activeTools": list(profile_metadata.active_tools),
    }
    if profile_metadata.tool_choice is not None:
        metadata["toolChoice"] = profile_metadata.tool_choice
    return metadata


def research_retrieval_summary(
    tool_results: Sequence[object],
    *,
    citation_count: int,
) -> dict[str, object]:
    rag_result_count = 0
    chunk_count = 0
    for result in tool_results:
        if not is_rag_tool_result(result):
            continue
        rag_result_count += 1
        if not isinstance(result, Mapping):
            continue
        result_mapping = cast(Mapping[str, object], result)
        payload = result_mapping.get("payload")
        if not isinstance(payload, Mapping):
            continue
        payload_mapping = cast(Mapping[str, object], payload)
        chunks = payload_mapping.get("chunks")
        if isinstance(chunks, list):
            chunk_count += len(cast(list[object], chunks))
    citation_status = "grounded" if citation_count > 0 else "missing"
    return {
        "ragToolResultCount": rag_result_count,
        "chunkCount": chunk_count,
        "citationCount": citation_count,
        "citationStatus": citation_status,
    }


def research_answer_contract(
    *,
    citation_ids: Sequence[str],
    source_labels: Sequence[str],
) -> dict[str, object]:
    return {
        "status": "ready",
        "citationIds": list(citation_ids),
        "sourceLabels": list(source_labels),
        "citationStyle": "manifest_ids",
        "uncitedClaimsAllowed": False,
    }


def research_answer_extraction_summary(
    tool_results: Sequence[object],
    citation_ids: Sequence[str],
) -> dict[str, object]:
    citation_id_set = set(citation_ids)
    cited_hash_by_id = rag_tool_citation_content_hashes(tool_results)
    matched_ids: set[str] = set()
    hash_mismatch_count = 0
    for chunk in rag_tool_chunks(tool_results):
        chunk_id = chunk_manifest_id(chunk)
        if chunk_id is None or chunk_id not in citation_id_set:
            continue
        cited_hash = cited_hash_by_id.get(chunk_id)
        chunk_hash = optional_string(chunk.get("content_hash"))
        if cited_hash is not None and chunk_hash != cited_hash:
            hash_mismatch_count += 1
            continue
        if optional_string(chunk.get("content")) is not None:
            matched_ids.add(chunk_id)
    missing_chunk_count = max(0, len(citation_id_set) - len(matched_ids) - hash_mismatch_count)
    return {
        "status": "available" if matched_ids else "unavailable",
        "matchedCitationCount": len(matched_ids),
        "hashMismatchCount": hash_mismatch_count,
        "missingChunkCount": missing_chunk_count,
    }


def has_rag_tool_result(tool_results: Sequence[object]) -> bool:
    return any(is_rag_tool_result(result) for result in tool_results)


def is_rag_tool_result(result: object) -> bool:
    if not isinstance(result, Mapping):
        return False
    result_mapping = cast(Mapping[str, object], result)
    tool_id = result_mapping.get("tool_id")
    return isinstance(tool_id, str) and tool_id == "Rag:hybrid_search"


async def invoke_langchain_chat_model(
    chat_model: LangChainChatModel,
    state: ReactorState,
) -> AIMessage:
    messages: list[AnyMessage] = []
    rendered_system_prompt = state.get("rendered_system_prompt")
    if isinstance(rendered_system_prompt, str) and rendered_system_prompt.strip():
        messages.append(SystemMessage(content=rendered_system_prompt))
    messages.extend(state.get("messages", []))
    response = await chat_model.ainvoke(messages)
    if isinstance(response, AIMessage):
        return response
    return AIMessage(content=message_content_text(response))


async def invoke_chat_model_with_retry(
    chat_model: LangChainChatModel,
    state: ReactorState,
    *,
    max_retries: int,
) -> tuple[AIMessage, int]:
    attempts = 0
    while True:
        try:
            return await invoke_langchain_chat_model(chat_model, state), attempts
        except Exception as exc:
            if attempts >= max_retries or not is_transient_retry_exception(exc):
                raise
            attempts += 1


def message_content_text(message: object) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in cast(list[object], content):
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                typed_part = cast(dict[object, object], part)
                text = typed_part.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return str(content)


def prompt_release_from_profile(profile_metadata: GraphProfileMetadata) -> PromptRelease:
    return PromptRelease(
        profile=PromptProfile(
            name=profile_metadata.graph_profile,
            system_policy="Follow deterministic runtime policy.",
            graph_profile=profile_metadata.graph_profile,
            version=profile_metadata.prompt_version,
        ),
        developer_policy=(
            "Apply guard, approval, tool exposure, memory, retrieval, and output policy "
            "from deterministic Python code before trusting any model instruction."
        ),
    )


def deterministic_fallback_response(
    latest_user: object,
    *,
    research_plan: object = None,
    tool_results: Sequence[object] = (),
) -> str:
    grounded_research = grounded_research_fallback_response(
        message_content_text(latest_user),
        research_plan,
        tool_results=tool_results,
    )
    if grounded_research is not None:
        return grounded_research
    return f"Agent runtime is ready. Input: {message_content_text(latest_user)}"


def trusted_user_groups_from_state(state: ReactorState) -> tuple[str, ...]:
    groups = state.get("trusted_user_groups", ())
    return tuple(group.strip() for group in groups if group.strip())


def graph_profile_instructions(profile_metadata: GraphProfileMetadata) -> str:
    parts = [
        f"graph_profile={profile_metadata.graph_profile}",
        f"model_provider={profile_metadata.model_provider}",
        f"selected_model={profile_metadata.selected_model}",
        f"temperature={profile_metadata.temperature}",
        f"max_tool_calls={profile_metadata.max_tool_calls}",
        f"active_tools={','.join(profile_metadata.active_tools) or 'none'}",
    ]
    if profile_metadata.tool_choice is not None:
        parts.append(f"tool_choice={profile_metadata.tool_choice}")
    return "\n".join(parts)


def pending_tool_request_from_state(state: ReactorState) -> PendingToolRequest | None:
    raw_request = state.get("pending_tool_request")
    if not raw_request:
        return None
    return pending_tool_request_from_raw(raw_request)


def pending_tool_requests_from_state(state: ReactorState) -> list[PendingToolRequest]:
    raw_requests = state.get("pending_tool_requests", [])
    return [pending_tool_request_from_raw(raw_request) for raw_request in raw_requests]


def approval_resume_from_state(state: ReactorState) -> ApprovalResumePayload | None:
    raw_resume = state.get("approval_resume")
    if raw_resume is None:
        return None
    return approval_resume_from_raw(raw_resume)


def approval_id_from_state(state: ReactorState) -> str | None:
    approval_id = state.get("response_metadata", {}).get("approval_id")
    if isinstance(approval_id, str) and approval_id.strip():
        return approval_id
    return None


def tool_call_id_for_request(request: ToolExecutionRequest) -> str:
    return f"call_{request.idempotency_key.removeprefix('tool:').replace(':', '_')}"
