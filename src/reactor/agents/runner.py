from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, cast

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command

from reactor.agents.graph import build_reactor_graph
from reactor.agents.langchain_agent import (
    LangChainAgentRunnable,
    LangChainInterruptAction,
    run_langchain_agent_once,
)
from reactor.agents.langchain_middleware import ChatModelSpec, LangChainMiddlewarePolicy
from reactor.agents.runtime_config import (
    LANGGRAPH_NATIVE_CONFIG_METADATA,
    LANGGRAPH_NATIVE_INVOKE_RUN_NAME,
    LANGGRAPH_NATIVE_RUN_TAGS,
    initial_reactor_state,
    langgraph_durable_config,
)
from reactor.agents.stores import GraphStore
from reactor.core.settings import Settings
from reactor.guards.input import InputGuardBlocked
from reactor.guards.output import OutputGuardBlocked
from reactor.kernel.ids import new_id
from reactor.providers.usage import TokenUsage, estimated_usage, usage_from_provider_metadata
from reactor.tools.catalog import ToolSpec
from reactor.tools.execution import ToolHandler

PUBLIC_RUN_METADATA_KEYS = frozenset(
    {
        "approval_id",
        "approval_status",
        "candidate_id",
        "checkpointProvenance",
        "checkpoint_ns",
        "contextManifest",
        "evalCaseId",
        "graph_profile",
        "guardBlock",
        "hook_failures",
        "hooks_status",
        "interrupt_action_status",
        "langchainMiddlewareChain",
        "langchainMiddlewarePolicy",
        "model_error_type",
        "model_fallback_used",
        "model_provider",
        "model_retry_count",
        "model_runtime",
        "output_boundary_status",
        "output_guard_status",
        "parallel_tool_count",
        "prompt_version",
        "research_plan",
        "resolvedToolProfileBudget",
        "response_filter_status",
        "selected_model",
        "state_schema_version",
        "stop_reason",
        "structuredOutput",
        "structured_output_allowed_citation_ids",
        "structured_output_citation_count",
        "structured_output_citation_policy",
        "structured_output_error_code",
        "structured_output_status",
        "structured_output_unsafe_citation_count",
        "temperature",
        "tokenUsage",
        "tool_cache_status",
        "tool_choice",
        "tool_output_guard_error_code",
        "tool_output_guard_findings",
        "tool_output_guard_status",
        "tool_profile_budget",
        "tool_risk_level",
        "tool_timeout_ms",
        "workflowTags",
    }
)

PUBLIC_APPROVAL_REQUEST_KEYS = frozenset(
    {
        "idempotency_key",
        "requested_by",
        "run_id",
        "tenant_id",
        "tool_id",
        "tool_risk_level",
        "tool_timeout_ms",
    }
)

PUBLIC_RESEARCH_PLAN_KEYS = frozenset(
    {
        "answerContract",
        "answerExtraction",
        "citationCount",
        "citationIds",
        "evidenceStatus",
        "executionProfile",
        "missingEvidence",
        "missingTool",
        "operatorAction",
        "profile",
        "reason",
        "recoverySteps",
        "requiredEvidence",
        "retrievalSummary",
        "sourceCount",
        "sourceLabels",
        "status",
        "verificationSteps",
    }
)

PUBLIC_RESEARCH_ANSWER_CONTRACT_KEYS = frozenset(
    {
        "citationIds",
        "citationStyle",
        "sourceLabels",
        "status",
        "uncitedClaimsAllowed",
    }
)

PRIVATE_PUBLIC_METADATA_KEY_MARKERS = (
    "api_key",
    "authorization",
    "credential",
    "input_payload",
    "password",
    "payload",
    "raw_",
    "secret",
    "token",
    "tool_args",
    "tool_arguments",
    "tool_input",
)

PRIVATE_PUBLIC_METADATA_EXACT_KEYS = frozenset(
    {
        "acl",
        "acl_groups",
        "acl_proof",
        "acl_users",
        "acl_visibility",
    }
)


@dataclass(frozen=True)
class RunResult:
    run_id: str
    tenant_id: str
    user_id: str
    thread_id: str
    checkpoint_ns: str
    status: str
    response: str
    provider: str
    model: str
    token_usage: TokenUsage | None = None
    response_metadata: dict[str, Any] = field(default_factory=lambda: {})
    interrupt_actions: tuple[LangChainInterruptAction, ...] = field(
        default_factory=tuple,
        repr=False,
    )

    def as_response(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "response": self.response,
            "metadata": public_run_metadata(self.response_metadata),
        }


@lru_cache(maxsize=1)
def compiled_graph():
    return build_reactor_graph()


def public_run_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    public: dict[str, object] = {}
    for key, value in metadata.items():
        if key not in PUBLIC_RUN_METADATA_KEYS:
            continue
        if key == "research_plan":
            public[key] = public_research_plan(value)
        else:
            public[key] = sanitize_public_metadata_value(value)
    approval_request = public_approval_request(metadata.get("approval_request"))
    if approval_request:
        public["approval_request"] = approval_request
    return public


def public_research_plan(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    public: dict[str, object] = {}
    for key, item in cast(Mapping[str, object], value).items():
        if key not in PUBLIC_RESEARCH_PLAN_KEYS:
            continue
        if key == "answerContract":
            answer_contract = public_research_answer_contract(item)
            if answer_contract:
                public[key] = answer_contract
        else:
            public[key] = sanitize_public_metadata_value(item)
    return public


def public_research_answer_contract(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    return {
        key: sanitize_public_metadata_value(item)
        for key, item in cast(Mapping[str, object], value).items()
        if key in PUBLIC_RESEARCH_ANSWER_CONTRACT_KEYS and not private_public_metadata_key(key)
    }


def sanitize_public_metadata_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): sanitize_public_metadata_value(item)
            for key, item in cast(Mapping[object, object], value).items()
            if not private_public_metadata_key(str(key))
        }
    if isinstance(value, list):
        return [sanitize_public_metadata_value(item) for item in cast(list[object], value)]
    if isinstance(value, tuple):
        return [sanitize_public_metadata_value(item) for item in cast(tuple[object, ...], value)]
    return value


def private_public_metadata_key(key: str) -> bool:
    lowered = key.lower()
    normalized = normalized_private_metadata_key(key)
    return (
        lowered in PRIVATE_PUBLIC_METADATA_EXACT_KEYS
        or normalized
        in {normalized_private_metadata_key(item) for item in PRIVATE_PUBLIC_METADATA_EXACT_KEYS}
        or lowered.startswith("acl_user_")
        or lowered.startswith("acl_group_")
        or any(marker in lowered for marker in PRIVATE_PUBLIC_METADATA_KEY_MARKERS)
        or any(
            normalized_private_metadata_key(marker) in normalized
            for marker in PRIVATE_PUBLIC_METADATA_KEY_MARKERS
        )
    )


def normalized_private_metadata_key(key: str) -> str:
    return "".join(character for character in key.lower() if character.isalnum())


def public_approval_request(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    return {
        key: sanitize_public_metadata_value(item)
        for key, item in cast(Mapping[str, object], value).items()
        if key in PUBLIC_APPROVAL_REQUEST_KEYS
    }


async def run_once(
    message: str,
    settings: Settings,
    run_id: str | None = None,
    graph: Any | None = None,
    tenant_id: str = "local",
    user_id: str = "anonymous",
    thread_id: str | None = None,
    checkpoint_ns: str | None = None,
    checkpoint_id: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    system_prompt: str | None = None,
    response_format: str | None = None,
    runtime: str = "langgraph",
    langchain_agent: LangChainAgentRunnable | None = None,
    tools: list[ToolSpec] | None = None,
    tool_handler: ToolHandler | None = None,
    tool_invocation_store: Any | None = None,
    structured_output_schema: object | None = None,
    checkpointer: object | None = None,
    graph_store: GraphStore | None = None,
    trusted_user_groups: tuple[str, ...] = (),
    fallback_models: Sequence[ChatModelSpec] = (),
    middleware_policy: LangChainMiddlewarePolicy | None = None,
    graph_profile: str | None = None,
    integration_context: dict[str, object] | None = None,
    context_manifest: Mapping[str, object] | None = None,
    resume_command: Command[Any] | None = None,
) -> RunResult:
    actual_run_id = run_id or new_id("run")
    actual_thread_id = thread_id or settings.default_thread_id
    actual_checkpoint_ns = checkpoint_ns or settings.default_checkpoint_ns
    actual_provider = provider or settings.default_model_provider
    actual_model = model or settings.default_model
    if runtime == "langchain_agent":
        try:
            agent_result = await asyncio.wait_for(
                run_langchain_agent_once(
                    message,
                    settings,
                    provider=actual_provider,
                    model=actual_model,
                    thread_id=actual_thread_id,
                    checkpoint_ns=actual_checkpoint_ns,
                    checkpoint_id=checkpoint_id,
                    agent=langchain_agent,
                    tools=tools,
                    tool_handler=tool_handler,
                    tool_invocation_store=tool_invocation_store,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    run_id=actual_run_id,
                    system_prompt=system_prompt,
                    response_format=response_format,
                    structured_output_schema=structured_output_schema,
                    checkpointer=checkpointer,
                    graph_store=graph_store,
                    trusted_user_groups=trusted_user_groups,
                    fallback_models=fallback_models,
                    middleware_policy=middleware_policy,
                    integration_context=integration_context,
                    context_manifest=context_manifest,
                    resume_command=resume_command,
                ),
                timeout=settings.agent_run_timeout_ms / 1000,
            )
        except TimeoutError:
            response = f"Agent run timed out after {settings.agent_run_timeout_ms}ms."
            return RunResult(
                run_id=actual_run_id,
                tenant_id=tenant_id,
                user_id=user_id,
                thread_id=actual_thread_id,
                checkpoint_ns=actual_checkpoint_ns,
                status="timeout",
                response=response,
                provider=actual_provider,
                model=actual_model,
                token_usage=estimated_usage(
                    message,
                    response,
                    max_output_tokens=settings.max_output_tokens,
                ),
            )
        except (InputGuardBlocked, OutputGuardBlocked) as error:
            return guard_block_result(
                error,
                run_id=actual_run_id,
                tenant_id=tenant_id,
                user_id=user_id,
                thread_id=actual_thread_id,
                checkpoint_ns=actual_checkpoint_ns,
                provider=actual_provider,
                model=actual_model,
                message=message,
                max_output_tokens=settings.max_output_tokens,
            )
        return RunResult(
            run_id=actual_run_id,
            tenant_id=tenant_id,
            user_id=user_id,
            thread_id=actual_thread_id,
            checkpoint_ns=actual_checkpoint_ns,
            status=(
                "interrupted"
                if getattr(agent_result, "interrupted", False)
                else response_policy_terminal_status(agent_result.response_metadata)
            ),
            response=agent_result.response,
            provider=actual_provider,
            model=actual_model,
            token_usage=agent_result.token_usage,
            response_metadata=agent_result.response_metadata,
            interrupt_actions=tuple(getattr(agent_result, "interrupt_actions", ())),
        )

    runnable = graph or (
        build_reactor_graph(tool_invocation_store=tool_invocation_store)
        if tool_invocation_store is not None
        else compiled_graph()
    )
    state = initial_reactor_state(
        run_id=actual_run_id,
        tenant_id=tenant_id,
        user_id=user_id,
        trusted_user_groups=trusted_user_groups,
        messages=[HumanMessage(content=message)],
        max_tool_calls=None if graph_profile is not None else settings.max_tool_calls,
        checkpoint_ns=actual_checkpoint_ns,
        request_system_prompt=system_prompt,
        model_provider=actual_provider,
        selected_model=actual_model,
        graph_profile=graph_profile,
        integration_context=integration_context,
        active_tools=[tool.qualified_name for tool in tools] if tools is not None else None,
        active_tool_specs=tool_state_specs(tools),
    )
    if response_format is not None and response_format.strip():
        state["response_format"] = response_format.strip()
    if isinstance(structured_output_schema, dict):
        state["response_schema"] = structured_output_schema
    try:
        result = await asyncio.wait_for(
            runnable.ainvoke(
                state,
                config=langgraph_durable_config(
                    tenant_id=tenant_id,
                    thread_id=actual_thread_id,
                    checkpoint_ns=actual_checkpoint_ns,
                    checkpoint_id=checkpoint_id,
                    run_name=LANGGRAPH_NATIVE_INVOKE_RUN_NAME,
                    tags=LANGGRAPH_NATIVE_RUN_TAGS,
                    metadata=LANGGRAPH_NATIVE_CONFIG_METADATA,
                ),
            ),
            timeout=settings.agent_run_timeout_ms / 1000,
        )
    except TimeoutError:
        response = f"Agent run timed out after {settings.agent_run_timeout_ms}ms."
        return RunResult(
            run_id=actual_run_id,
            tenant_id=tenant_id,
            user_id=user_id,
            thread_id=actual_thread_id,
            checkpoint_ns=actual_checkpoint_ns,
            status="timeout",
            response=response,
            provider=actual_provider,
            model=actual_model,
            token_usage=estimated_usage(
                message,
                response,
                max_output_tokens=settings.max_output_tokens,
            ),
        )
    except OutputGuardBlocked as error:
        return guard_block_result(
            error,
            run_id=actual_run_id,
            tenant_id=tenant_id,
            user_id=user_id,
            thread_id=actual_thread_id,
            checkpoint_ns=actual_checkpoint_ns,
            provider=actual_provider,
            model=actual_model,
            message=message,
            max_output_tokens=settings.max_output_tokens,
        )
    except InputGuardBlocked as error:
        return guard_block_result(
            error,
            run_id=actual_run_id,
            tenant_id=tenant_id,
            user_id=user_id,
            thread_id=actual_thread_id,
            checkpoint_ns=actual_checkpoint_ns,
            provider=actual_provider,
            model=actual_model,
            message=message,
            max_output_tokens=settings.max_output_tokens,
        )
    native_interrupts = native_langgraph_interrupts(result)
    interrupt_actions = extract_native_langgraph_interrupt_actions(native_interrupts)
    interrupted = bool(native_interrupts)
    response = (
        "Agent run paused for approval." if interrupted else str(result.get("response_text", ""))
    )
    response_metadata = (
        {
            "approval_status": "pending",
            "stop_reason": "langgraph_interrupt",
        }
        if interrupted
        else metadata_from_graph_result(result)
    )
    provider_usage = latest_provider_usage(result, max_output_tokens=settings.max_output_tokens)
    return RunResult(
        run_id=actual_run_id,
        tenant_id=tenant_id,
        user_id=user_id,
        thread_id=actual_thread_id,
        checkpoint_ns=actual_checkpoint_ns,
        status=(
            "interrupted" if interrupted else response_policy_terminal_status(response_metadata)
        ),
        response=response,
        provider=actual_provider,
        model=actual_model,
        token_usage=provider_usage
        or estimated_usage(
            message,
            response,
            max_output_tokens=settings.max_output_tokens,
        ),
        response_metadata=response_metadata,
        interrupt_actions=interrupt_actions,
    )


def tool_state_specs(tools: Sequence[ToolSpec] | None) -> list[dict[str, object]] | None:
    if tools is None:
        return None
    return [
        {
            "qualified_name": tool.qualified_name,
            "risk_level": tool.risk_level,
        }
        for tool in tools
    ]


def response_policy_terminal_status(
    response_metadata: Mapping[str, object],
    *,
    default: str = "completed",
) -> str:
    if response_metadata.get("stop_reason") in {
        "structured_output_invalid",
        "tool_output_guard_blocked",
    }:
        return "rejected"
    if response_metadata.get("stop_reason") == "interrupt_action_invalid":
        return "failed"
    return default


def guard_block_result(
    error: InputGuardBlocked | OutputGuardBlocked,
    *,
    run_id: str,
    tenant_id: str,
    user_id: str,
    thread_id: str,
    checkpoint_ns: str,
    provider: str,
    model: str,
    message: str,
    max_output_tokens: int,
) -> RunResult:
    metadata = sanitized_guard_block_metadata(
        error,
        run_id=run_id,
        tenant_id=tenant_id,
    )
    response = guard_block_response(metadata)
    return RunResult(
        run_id=run_id,
        tenant_id=tenant_id,
        user_id=user_id,
        thread_id=thread_id,
        checkpoint_ns=checkpoint_ns,
        status="rejected",
        response=response,
        provider=provider,
        model=model,
        token_usage=estimated_usage(
            message,
            response,
            max_output_tokens=max_output_tokens,
        ),
        response_metadata={"guardBlock": metadata},
    )


def sanitized_guard_block_metadata(
    error: InputGuardBlocked | OutputGuardBlocked,
    *,
    run_id: str,
    tenant_id: str,
) -> dict[str, object]:
    metadata = error.as_metadata()
    stage = str(metadata.get("stage") or "guard")
    return {
        "stage": stage,
        "reason": error.reason,
        "run_id": run_id,
        "tenant_id": tenant_id,
        "graph_node": str(metadata.get("graph_node") or default_guard_graph_node(stage)),
    }


def default_guard_graph_node(stage: str) -> str:
    return "guard" if stage == "input_guard" else "output_guard"


def guard_block_response(metadata: Mapping[str, object]) -> str:
    if metadata.get("stage") == "input_guard":
        return "Request blocked by input guard policy."
    return "Response blocked by output guard policy."


def metadata_from_graph_result(graph_result: dict[str, Any]) -> dict[str, Any]:
    raw_metadata = graph_result.get("response_metadata")
    if not isinstance(raw_metadata, Mapping):
        return {}
    return dict(cast(Mapping[str, Any], raw_metadata))


def native_langgraph_interrupts(graph_result: Mapping[str, object]) -> tuple[object, ...]:
    raw_interrupts = graph_result.get("__interrupt__")
    if not isinstance(raw_interrupts, Sequence) or isinstance(
        raw_interrupts,
        str | bytes | bytearray,
    ):
        return ()
    return tuple(cast(Sequence[object], raw_interrupts))


def extract_native_langgraph_interrupt_actions(
    interrupts: Sequence[object],
) -> tuple[LangChainInterruptAction, ...]:
    actions: list[LangChainInterruptAction] = []
    for interrupt in interrupts:
        value = getattr(interrupt, "value", interrupt)
        if not isinstance(value, Mapping):
            return ()
        approval_request = cast(Mapping[object, object], value).get("approval_request")
        if not isinstance(approval_request, Mapping):
            return ()
        request_mapping = cast(Mapping[object, object], approval_request)
        tool_name = request_mapping.get("tool_id")
        arguments = request_mapping.get("input_payload")
        if (
            not isinstance(tool_name, str)
            or not tool_name.strip()
            or not isinstance(arguments, Mapping)
        ):
            return ()
        argument_mapping = cast(Mapping[object, object], arguments)
        if not all(isinstance(key, str) for key in argument_mapping):
            return ()
        actions.append(
            LangChainInterruptAction(
                tool_name=tool_name.strip(),
                arguments=dict(cast(Mapping[str, Any], argument_mapping)),
            )
        )
    return tuple(actions)


def latest_provider_usage(
    graph_result: dict[str, Any],
    *,
    max_output_tokens: int,
) -> TokenUsage | None:
    messages = graph_result.get("messages")
    if not isinstance(messages, list):
        return None
    typed_messages = cast(list[object], messages)
    for message in reversed(typed_messages):
        if isinstance(message, AIMessage):
            usage = usage_from_provider_metadata(
                message,
                max_output_tokens=max_output_tokens,
            )
            if usage is not None:
                return usage
    return None
