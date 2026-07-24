from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import asdict, dataclass, field, is_dataclass
from importlib import import_module
from typing import Any, Protocol, cast

from langchain.agents.structured_output import AutoStrategy
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Command

from reactor.agents.interrupts import validate_langchain_hitl_resume_command
from reactor.agents.langchain_middleware import (
    ChatModelSpec,
    LangChainMiddlewarePolicy,
    build_langchain_agent_middleware,
    planned_langchain_middleware_names,
)
from reactor.agents.runtime_config import langgraph_durable_config
from reactor.agents.stores import GraphStore
from reactor.agents.streaming import LANGCHAIN_AGENT_STREAM_EVENTS_VERSION
from reactor.context.assembler import RAG_GROUNDING_POLICY, render_integration_context
from reactor.context.manifest import CONTEXT_SECTION_RANK, ContextSection, safe_manifest_metadata
from reactor.core.settings import Settings
from reactor.kernel.citations import bounded_citation_evidence
from reactor.providers.chat_models import ChatModelFactory, LangChainChatModelFactory
from reactor.providers.usage import TokenUsage, estimated_usage, usage_from_provider_metadata
from reactor.response.structured import (
    ResponseFormat,
    StructuredResponseRepairer,
    context_manifest_citation_ids,
    context_manifest_requires_citations,
    context_manifest_unsafe_citation_count,
    extract_response_format,
    merge_citation_response_schema,
)
from reactor.tools.catalog import ToolSpec
from reactor.tools.execution import ToolHandler, ToolPolicy
from reactor.tools.langchain_adapter import (
    REACTOR_TOOL_ARTIFACT_SCHEMA,
    ToolInvocationAuditStore,
    build_langchain_tools,
    rag_context_manifest_metadata_from_payload,
)
from reactor.tools.sanitizer import TOOL_OUTPUT_SANITIZER_FINDINGS

LANGCHAIN_AGENTS_MODULE = cast(Any, import_module("langchain.agents"))
LANGCHAIN_CREATE_AGENT: Any = LANGCHAIN_AGENTS_MODULE.create_agent
LANGCHAIN_AGENT_GRAPH_NAME = "reactor-langchain-agent"
LANGCHAIN_AGENT_INVOKE_RUN_NAME = "reactor.langchain_agent.invoke"
LANGCHAIN_AGENT_INVOKE_VERSION = "v2"
LANGCHAIN_AGENT_STREAM_RUN_NAME = "reactor.langchain_agent.stream"
LANGCHAIN_AGENT_RUN_TAGS = ("reactor", "runtime:langchain_agent")
LANGCHAIN_AGENT_CONFIG_METADATA = {"reactor.runtime": "langchain_agent"}
_STRUCTURED_RESPONSE_SERIALIZATION_FAILURE = "\x00reactor:structured-response-serialization-failed"


def empty_response_metadata() -> dict[str, object]:
    return {}


class LangChainAgentRunnable(Protocol):
    async def ainvoke(
        self,
        input: object,
        config: RunnableConfig | None = None,
        *,
        version: str = LANGCHAIN_AGENT_INVOKE_VERSION,
    ) -> Any:
        pass

    def astream_events(
        self,
        input: dict[str, object],
        config: RunnableConfig | None = None,
        *,
        version: str,
    ) -> AsyncIterator[Mapping[str, object]]: ...


@dataclass(frozen=True)
class LangChainInterruptAction:
    tool_name: str
    arguments: dict[str, Any] = field(repr=False)


@dataclass(frozen=True)
class LangChainAgentResult:
    response: str
    token_usage: TokenUsage | None = None
    response_metadata: dict[str, object] = field(default_factory=empty_response_metadata)
    interrupted: bool = False
    interrupt_actions: tuple[LangChainInterruptAction, ...] = field(
        default_factory=tuple,
        repr=False,
    )


@dataclass(frozen=True)
class DurableInterruptMessageRecovery:
    messages: tuple[BaseMessage, ...] = field(default_factory=tuple)
    read_failed: bool = False


@dataclass(frozen=True)
class StructuredBoundaryResult:
    response: str
    metadata: dict[str, object] = field(default_factory=empty_response_metadata)


def model_identifier(provider: str, model: str) -> str:
    return f"{provider}:{model}" if provider.strip() else model


def resolve_langchain_agent_models(
    *,
    provider: str,
    model: str,
    fallback_models: Sequence[ChatModelSpec],
    chat_model_factory: ChatModelFactory | None = None,
) -> tuple[Any, tuple[ChatModelSpec, ...]]:
    factory = chat_model_factory or LangChainChatModelFactory()
    primary_identifier = model_identifier(provider.strip(), model.strip())
    for fallback in fallback_models:
        if not isinstance(fallback, str):
            continue
        fallback_provider, separator, fallback_model = fallback.strip().partition(":")
        fallback_identifier = model_identifier(
            fallback_provider.strip() if separator else "",
            fallback_model.strip() if separator else fallback_provider.strip(),
        )
        if fallback_identifier == primary_identifier:
            raise ValueError("fallback model must differ from primary model")
    primary_model = factory.create(provider=provider, model=model)
    resolved_fallbacks: list[ChatModelSpec] = []
    for fallback in fallback_models:
        if not isinstance(fallback, str):
            resolved_fallbacks.append(fallback)
            continue
        fallback_provider, separator, fallback_model = fallback.partition(":")
        resolved_fallbacks.append(
            factory.create(
                provider=fallback_provider if separator else "",
                model=fallback_model if separator else fallback_provider,
            )
        )
    return primary_model, tuple(resolved_fallbacks)


def langchain_response_format(
    response_format: str | None,
    structured_output_schema: object | None = None,
) -> object | None:
    if structured_output_schema is not None:
        return structured_output_schema
    if extract_response_format(response_format) != ResponseFormat.JSON:
        return None
    return cast(object, AutoStrategy(schema={"type": "object", "additionalProperties": True}))


def build_langchain_agent(
    settings: Settings,
    *,
    provider: str,
    model: str,
    system_prompt: str | None = None,
    interrupt_on_tools: tuple[str, ...] = (),
    tools: Sequence[object] | None = None,
    response_format: str | None = None,
    structured_output_schema: object | None = None,
    checkpointer: object | None = None,
    graph_store: GraphStore | None = None,
    fallback_models: Sequence[ChatModelSpec] = (),
    middleware_policy: LangChainMiddlewarePolicy | None = None,
    middleware: Sequence[object] | None = None,
    chat_model_factory: ChatModelFactory | None = None,
    primary_model: ChatModelSpec | None = None,
) -> LangChainAgentRunnable:
    actual_primary_model = primary_model
    actual_fallback_models = tuple(fallback_models)
    if actual_primary_model is None:
        actual_primary_model, actual_fallback_models = resolve_langchain_agent_models(
            provider=provider,
            model=model,
            fallback_models=fallback_models,
            chat_model_factory=chat_model_factory,
        )
    actual_middleware = (
        list(middleware)
        if middleware is not None
        else build_langchain_agent_middleware(
            settings,
            interrupt_on_tools=interrupt_on_tools,
            fallback_models=actual_fallback_models,
            policy=middleware_policy,
        )
    )
    return cast(
        LangChainAgentRunnable,
        LANGCHAIN_CREATE_AGENT(
            model=actual_primary_model,
            tools=tools or [],
            system_prompt=system_prompt,
            middleware=actual_middleware,
            response_format=langchain_response_format(
                response_format,
                structured_output_schema,
            ),
            checkpointer=checkpointer,
            store=graph_store,
            name=LANGCHAIN_AGENT_GRAPH_NAME,
        ),
    )


async def run_langchain_agent_once(
    message: str,
    settings: Settings,
    *,
    provider: str,
    model: str,
    thread_id: str,
    checkpoint_ns: str,
    checkpoint_id: str | None = None,
    system_prompt: str | None = None,
    agent: LangChainAgentRunnable | None = None,
    tools: list[ToolSpec] | None = None,
    tool_handler: ToolHandler | None = None,
    tool_invocation_store: ToolInvocationAuditStore | None = None,
    tenant_id: str = "local",
    user_id: str = "anonymous",
    trusted_user_groups: tuple[str, ...] = (),
    run_id: str = "run",
    response_format: str | None = None,
    structured_output_schema: object | None = None,
    checkpointer: object | None = None,
    graph_store: GraphStore | None = None,
    fallback_models: Sequence[ChatModelSpec] = (),
    middleware_policy: LangChainMiddlewarePolicy | None = None,
    chat_model_factory: ChatModelFactory | None = None,
    integration_context: dict[str, object] | None = None,
    context_manifest: Mapping[str, object] | None = None,
    resume_command: Command[Any] | None = None,
) -> LangChainAgentResult:
    if resume_command is not None:
        validate_langchain_hitl_resume_command(resume_command)
    interrupt_on_tools = approval_required_tool_names(tools)
    langchain_tools = []
    if tools is not None and tool_handler is not None:
        langchain_tools = build_langchain_tools(
            tools,
            handler=tool_handler,
            run_id=run_id,
            tenant_id=tenant_id,
            user_id=user_id,
            trusted_user_groups=trusted_user_groups,
            policy=ToolPolicy(
                allow_write_without_approval=agent is None and bool(interrupt_on_tools),
            ),
            tool_invocation_store=tool_invocation_store,
        )
    effective_system_prompt = system_prompt_with_integration_context(
        system_prompt,
        integration_context=integration_context,
        active_tools=model_facing_tool_names(tools, tool_handler=tool_handler),
    )
    middleware_chain: list[object] = []
    if agent is None:
        primary_model: ChatModelSpec | None = None
        resolved_fallback_models = tuple(fallback_models)
        if fallback_models:
            primary_model, resolved_fallback_models = resolve_langchain_agent_models(
                provider=provider,
                model=model,
                fallback_models=fallback_models,
                chat_model_factory=chat_model_factory,
            )
        middleware_chain = build_langchain_agent_middleware(
            settings,
            interrupt_on_tools=interrupt_on_tools,
            retry_on_tools=retryable_tool_names(tools),
            fallback_models=resolved_fallback_models,
            policy=middleware_policy,
        )
        runnable = build_langchain_agent(
            settings,
            provider=provider,
            model=model,
            system_prompt=effective_system_prompt,
            interrupt_on_tools=interrupt_on_tools,
            tools=langchain_tools,
            response_format=response_format,
            structured_output_schema=structured_output_schema,
            checkpointer=checkpointer,
            graph_store=graph_store,
            fallback_models=resolved_fallback_models,
            middleware_policy=middleware_policy,
            middleware=middleware_chain,
            chat_model_factory=chat_model_factory,
            primary_model=primary_model,
        )
    else:
        runnable = agent
    invoke_config = langgraph_durable_config(
        tenant_id=tenant_id,
        thread_id=thread_id,
        checkpoint_ns=checkpoint_ns,
        checkpoint_id=checkpoint_id,
        run_name=LANGCHAIN_AGENT_INVOKE_RUN_NAME,
        tags=LANGCHAIN_AGENT_RUN_TAGS,
        metadata=LANGCHAIN_AGENT_CONFIG_METADATA,
    )
    result = await runnable.ainvoke(
        (
            resume_command
            if resume_command is not None
            else {"messages": [HumanMessage(content=message)]}
        ),
        config=invoke_config,
        version=LANGCHAIN_AGENT_INVOKE_VERSION,
    )
    result_value = graph_output_value(result)
    messages = extract_messages(result_value)
    interrupts = graph_output_interrupts(result)
    interrupt_actions = extract_langchain_interrupt_actions(interrupts) if interrupts else ()
    if interrupts and len(interrupt_actions) != 1:
        invalid_response = "Agent run failed because interrupt actions were invalid."
        invalid_response_metadata: dict[str, object] = {
            "stop_reason": "interrupt_action_invalid",
            "interrupt_action_status": "invalid",
        }
        add_langchain_tool_output_guard_metadata(
            invalid_response_metadata,
            messages=messages,
            context_manifest=context_manifest_with_runtime_rag_citations(
                context_manifest,
                messages=messages,
                runtime_snapshot=True,
            ),
        )
        if middleware_chain:
            invalid_response_metadata["langchainMiddlewareChain"] = (
                langchain_middleware_chain_metadata(
                    middleware_chain,
                    interrupt_on_tools=interrupt_on_tools,
                    fallback_models=fallback_models,
                )
            )
        return LangChainAgentResult(
            response=invalid_response,
            response_metadata=invalid_response_metadata,
            token_usage=latest_provider_usage(
                messages,
                max_output_tokens=settings.max_output_tokens,
            )
            or estimated_usage(
                message,
                invalid_response,
                max_output_tokens=settings.max_output_tokens,
            ),
        )
    checkpoint_recovery = DurableInterruptMessageRecovery()
    if interrupts:
        checkpoint_recovery = await durable_interrupt_messages(
            checkpointer,
            config=invoke_config,
        )
        if checkpoint_recovery.messages:
            messages = list(checkpoint_recovery.messages)
    effective_context_manifest = context_manifest_with_runtime_rag_citations(
        context_manifest,
        messages=messages,
        runtime_snapshot=True,
    )
    if interrupts:
        response_metadata: dict[str, object] = {
            "approval_status": "pending",
            "stop_reason": "langchain_interrupt",
        }
        if checkpoint_recovery.read_failed:
            response_metadata["checkpointEvidenceRecovery"] = {
                "status": "failed",
                "operation": "latest_checkpoint_read",
                "fallback": "graph_output_messages",
            }
        add_langchain_tool_output_guard_metadata(
            response_metadata,
            messages=messages,
            context_manifest=effective_context_manifest,
        )
        if response_metadata.get("tool_output_guard_status") == "blocked":
            blocked_response = "Response blocked by tool output guard policy."
            return LangChainAgentResult(
                response=blocked_response,
                response_metadata=response_metadata,
                token_usage=latest_provider_usage(
                    messages,
                    max_output_tokens=settings.max_output_tokens,
                )
                or estimated_usage(
                    message,
                    blocked_response,
                    max_output_tokens=settings.max_output_tokens,
                ),
            )
        if middleware_chain:
            response_metadata["langchainMiddlewareChain"] = langchain_middleware_chain_metadata(
                middleware_chain,
                interrupt_on_tools=interrupt_on_tools,
                fallback_models=fallback_models,
            )
        interrupted_response = "Agent run paused for approval."
        return LangChainAgentResult(
            response=interrupted_response,
            response_metadata=response_metadata,
            token_usage=latest_provider_usage(
                messages,
                max_output_tokens=settings.max_output_tokens,
            )
            or estimated_usage(
                message,
                interrupted_response,
                max_output_tokens=settings.max_output_tokens,
            ),
            interrupted=True,
            interrupt_actions=interrupt_actions,
        )
    structured_response = extract_structured_response(
        result_value,
        structured_output_schema=structured_output_schema,
    )
    has_structured_response = (
        isinstance(result_value, dict) and "structured_response" in result_value
    )
    raw_response = (
        structured_response if has_structured_response else extract_response_text(messages)
    )
    if raw_response is None:
        raw_response = ""
    boundary_result = await enforce_structured_response_boundary_with_metadata(
        raw_response,
        response_format=response_format,
        structured_output_schema=structured_output_schema,
        context_manifest=effective_context_manifest,
    )
    response_metadata = dict(boundary_result.metadata)
    add_langchain_tool_output_guard_metadata(
        response_metadata,
        messages=messages,
        context_manifest=effective_context_manifest,
    )
    response = boundary_result.response
    if response_metadata.get("tool_output_guard_status") == "blocked":
        response = "Response blocked by tool output guard policy."
    if middleware_chain:
        response_metadata["langchainMiddlewareChain"] = langchain_middleware_chain_metadata(
            middleware_chain,
            interrupt_on_tools=interrupt_on_tools,
            fallback_models=fallback_models,
        )
    return LangChainAgentResult(
        response=response,
        response_metadata=response_metadata,
        token_usage=latest_provider_usage(messages, max_output_tokens=settings.max_output_tokens)
        or estimated_usage(
            message,
            response,
            max_output_tokens=settings.max_output_tokens,
        ),
    )


async def stream_langchain_agent_events(
    message: str,
    settings: Settings,
    *,
    provider: str,
    model: str,
    thread_id: str,
    checkpoint_ns: str,
    checkpoint_id: str | None = None,
    system_prompt: str | None = None,
    agent: LangChainAgentRunnable | None = None,
    tools: list[ToolSpec] | None = None,
    tool_handler: ToolHandler | None = None,
    tool_invocation_store: ToolInvocationAuditStore | None = None,
    tenant_id: str = "local",
    user_id: str = "anonymous",
    trusted_user_groups: tuple[str, ...] = (),
    run_id: str = "run",
    response_format: str | None = None,
    structured_output_schema: object | None = None,
    checkpointer: object | None = None,
    graph_store: GraphStore | None = None,
    fallback_models: Sequence[ChatModelSpec] = (),
    middleware_policy: LangChainMiddlewarePolicy | None = None,
    chat_model_factory: ChatModelFactory | None = None,
    integration_context: dict[str, object] | None = None,
    context_manifest: Mapping[str, object] | None = None,
) -> AsyncIterator[Mapping[str, object]]:
    interrupt_on_tools = approval_required_tool_names(tools)
    langchain_tools = []
    if tools is not None and tool_handler is not None:
        langchain_tools = build_langchain_tools(
            tools,
            handler=tool_handler,
            run_id=run_id,
            tenant_id=tenant_id,
            user_id=user_id,
            trusted_user_groups=trusted_user_groups,
            policy=ToolPolicy(
                allow_write_without_approval=agent is None and bool(interrupt_on_tools),
            ),
            tool_invocation_store=tool_invocation_store,
        )
    effective_system_prompt = system_prompt_with_integration_context(
        system_prompt,
        integration_context=integration_context,
        active_tools=model_facing_tool_names(tools, tool_handler=tool_handler),
    )
    if agent is None:
        primary_model: ChatModelSpec | None = None
        resolved_fallback_models = tuple(fallback_models)
        if fallback_models:
            primary_model, resolved_fallback_models = resolve_langchain_agent_models(
                provider=provider,
                model=model,
                fallback_models=fallback_models,
                chat_model_factory=chat_model_factory,
            )
        middleware_chain = build_langchain_agent_middleware(
            settings,
            interrupt_on_tools=interrupt_on_tools,
            retry_on_tools=retryable_tool_names(tools),
            fallback_models=resolved_fallback_models,
            policy=middleware_policy,
        )
        runnable = build_langchain_agent(
            settings,
            provider=provider,
            model=model,
            system_prompt=effective_system_prompt,
            interrupt_on_tools=interrupt_on_tools,
            tools=langchain_tools,
            response_format=response_format,
            structured_output_schema=structured_output_schema,
            checkpointer=checkpointer,
            graph_store=graph_store,
            fallback_models=resolved_fallback_models,
            middleware_policy=middleware_policy,
            middleware=middleware_chain,
            chat_model_factory=chat_model_factory,
            primary_model=primary_model,
        )
    else:
        runnable = agent
    event_stream = runnable.astream_events(
        {"messages": [HumanMessage(content=message)]},
        config=langgraph_durable_config(
            tenant_id=tenant_id,
            thread_id=thread_id,
            checkpoint_ns=checkpoint_ns,
            checkpoint_id=checkpoint_id,
            run_name=LANGCHAIN_AGENT_STREAM_RUN_NAME,
            tags=LANGCHAIN_AGENT_RUN_TAGS,
            metadata=LANGCHAIN_AGENT_CONFIG_METADATA,
        ),
        version=LANGCHAIN_AGENT_STREAM_EVENTS_VERSION,
    )
    async for event in event_stream:
        yield event


def approval_required_tool_names(tools: Sequence[ToolSpec] | None) -> tuple[str, ...]:
    if tools is None:
        return ()
    return tuple(tool.qualified_name for tool in tools if tool.enabled and tool.approval_required)


def retryable_tool_names(tools: Sequence[ToolSpec] | None) -> tuple[str, ...]:
    if tools is None:
        return ()
    return tuple(
        tool.qualified_name
        for tool in tools
        if tool.enabled and tool.risk_level == "read" and not tool.approval_required
    )


def langchain_middleware_chain_metadata(
    middleware: Sequence[object],
    *,
    interrupt_on_tools: Sequence[str] = (),
    fallback_models: Sequence[ChatModelSpec] = (),
) -> dict[str, object]:
    middleware_names = [type(item).__name__ for item in middleware]
    return langchain_middleware_names_metadata(
        middleware_names,
        interrupt_on_tools=interrupt_on_tools,
        fallback_models=fallback_models,
    )


def planned_langchain_middleware_chain_metadata(
    settings: Settings,
    *,
    interrupt_on_tools: Sequence[str] = (),
    fallback_models: Sequence[ChatModelSpec] = (),
    policy: LangChainMiddlewarePolicy | None = None,
) -> dict[str, object]:
    return langchain_middleware_names_metadata(
        planned_langchain_middleware_names(
            settings,
            interrupt_on_tools=interrupt_on_tools,
            fallback_models=fallback_models,
            policy=policy,
        ),
        interrupt_on_tools=interrupt_on_tools,
        fallback_models=fallback_models,
    )


def langchain_middleware_names_metadata(
    middleware_names: Sequence[str],
    *,
    interrupt_on_tools: Sequence[str],
    fallback_models: Sequence[ChatModelSpec],
) -> dict[str, object]:
    return {
        "status": "applied",
        "count": len(middleware_names),
        "middleware": list(middleware_names),
        "piiRuleCount": middleware_names.count("PIIMiddleware"),
        "hitlToolCount": len(interrupt_on_tools),
        "fallbackModelCount": len(fallback_models),
    }


def model_facing_tool_names(
    tools: Sequence[ToolSpec] | None,
    *,
    tool_handler: ToolHandler | None,
) -> tuple[str, ...]:
    if tools is None or tool_handler is None:
        return ()
    return tuple(tool.qualified_name for tool in tools if tool.enabled)


def system_prompt_with_integration_context(
    system_prompt: str | None,
    *,
    integration_context: dict[str, object] | None,
    active_tools: Sequence[str],
) -> str | None:
    rendered_context = render_integration_context(
        integration_context,
        active_tools=active_tools,
    )
    if rendered_context == "none":
        return system_prompt
    context_block = f"[integration_context]\n{rendered_context}"
    if system_prompt is None or not system_prompt.strip():
        return context_block
    return f"{system_prompt.rstrip()}\n\n{context_block}"


def extract_messages(result: object) -> list[BaseMessage]:
    if isinstance(result, dict):
        messages = cast(object, result.get("messages"))
        if isinstance(messages, list):
            return [
                message
                for message in cast(list[object], messages)
                if isinstance(message, BaseMessage)
            ]
    return []


async def durable_interrupt_messages(
    checkpointer: object | None,
    *,
    config: RunnableConfig,
) -> DurableInterruptMessageRecovery:
    if not isinstance(checkpointer, BaseCheckpointSaver):
        return DurableInterruptMessageRecovery()
    try:
        checkpoint_tuple = await cast(BaseCheckpointSaver[Any], checkpointer).aget_tuple(
            latest_checkpoint_read_config(config)
        )
    except Exception:
        return DurableInterruptMessageRecovery(read_failed=True)
    if checkpoint_tuple is None:
        return DurableInterruptMessageRecovery()
    checkpoint = checkpoint_tuple.checkpoint
    channel_values = checkpoint.get("channel_values")
    return DurableInterruptMessageRecovery(messages=tuple(extract_messages(channel_values)))


def latest_checkpoint_read_config(config: RunnableConfig) -> RunnableConfig:
    configurable = config.get("configurable")
    if not isinstance(configurable, Mapping) or "checkpoint_id" not in configurable:
        return config
    latest_config = dict(config)
    latest_configurable = dict(cast(Mapping[str, object], configurable))
    latest_configurable.pop("checkpoint_id", None)
    latest_config["configurable"] = latest_configurable
    return cast(RunnableConfig, latest_config)


def add_langchain_tool_output_guard_metadata(
    response_metadata: dict[str, object],
    *,
    messages: Sequence[BaseMessage],
    context_manifest: Mapping[str, object] | None,
) -> dict[str, object] | None:
    tool_output_guard = langchain_tool_output_guard(messages)
    if tool_output_guard is None:
        return None
    metadata, model_visible_outputs = tool_output_guard
    findings = cast(list[str], metadata["findings"])
    if findings:
        response_metadata["tool_output_guard_findings"] = findings
    error_code = tool_output_guard_error_code(metadata)
    if error_code is not None:
        response_metadata.update(
            {
                "stop_reason": "tool_output_guard_blocked",
                "tool_output_guard_error_code": error_code,
                "tool_output_guard_status": "blocked",
            }
        )
    response_metadata["contextManifest"] = context_manifest_with_tool_output_guard(
        context_manifest,
        metadata=metadata,
        model_visible_outputs=model_visible_outputs,
    )
    return metadata


def langchain_tool_output_guard(
    messages: Sequence[BaseMessage],
) -> tuple[dict[str, object], list[str]] | None:
    model_visible_outputs: list[str] = []
    findings: list[str] = []
    artifact_content_mismatch_count = 0
    unlabeled_output_count = 0
    for message in messages:
        if not isinstance(message, ToolMessage):
            continue
        artifact: Mapping[str, object] = (
            cast(Mapping[str, object], message.artifact)
            if isinstance(message.artifact, Mapping)
            else {}
        )
        artifact_text = artifact.get("model_visible_text")
        model_visible_text = message.content if isinstance(message.content, str) else None
        if isinstance(artifact_text, str) and artifact_text != model_visible_text:
            artifact_content_mismatch_count += 1
        if not isinstance(model_visible_text, str) or not model_visible_text.startswith(
            "[tool_output:data]\n"
        ):
            unlabeled_output_count += 1
            continue
        model_visible_outputs.append(model_visible_text)
        raw_findings = artifact.get("sanitizer_findings")
        if not isinstance(raw_findings, Sequence) or isinstance(
            raw_findings,
            str | bytes | bytearray,
        ):
            continue
        findings.extend(
            finding
            for finding in cast(Sequence[object], raw_findings)
            if isinstance(finding, str) and finding in TOOL_OUTPUT_SANITIZER_FINDINGS
        )
    if (
        not model_visible_outputs
        and artifact_content_mismatch_count == 0
        and unlabeled_output_count == 0
    ):
        return None
    metadata: dict[str, object] = {
        "output_count": len(model_visible_outputs),
        "sanitized_count": len(model_visible_outputs),
        "findings": list(dict.fromkeys(findings)),
    }
    if artifact_content_mismatch_count:
        metadata["artifact_content_mismatch_count"] = artifact_content_mismatch_count
    if unlabeled_output_count:
        metadata["unlabeled_output_count"] = unlabeled_output_count
    return (
        metadata,
        model_visible_outputs,
    )


def tool_output_guard_error_code(metadata: Mapping[str, object]) -> str | None:
    if metadata.get("artifact_content_mismatch_count", 0) != 0:
        return "ARTIFACT_CONTENT_MISMATCH"
    if metadata.get("unlabeled_output_count", 0) != 0:
        return "UNLABELED_TOOL_OUTPUT"
    return None


def langchain_v2_stream_tool_messages(
    raw_event: Mapping[str, object],
) -> list[ToolMessage]:
    if raw_event.get("event") != "on_tool_end":
        return []
    data = raw_event.get("data")
    if not isinstance(data, Mapping):
        return []
    output = cast(Mapping[object, object], data).get("output")
    if isinstance(output, ToolMessage):
        return [output]
    if isinstance(output, Command):
        output = output.update
    if isinstance(output, Mapping):
        mapping_output = cast(Mapping[object, object], output)
        return [
            message
            for message in extract_messages({"messages": mapping_output.get("messages")})
            if isinstance(message, ToolMessage)
        ]
    if not isinstance(output, Sequence) or isinstance(output, str | bytes | bytearray):
        return []
    return [
        message for message in cast(Sequence[object], output) if isinstance(message, ToolMessage)
    ]


def langchain_v2_stream_structured_response(
    raw_event: Mapping[str, object],
    *,
    structured_output_schema: object | None = None,
) -> str | None:
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
    return extract_structured_response(
        output,
        structured_output_schema=structured_output_schema,
    )


def context_manifest_with_runtime_rag_citations(
    context_manifest: Mapping[str, object] | None,
    *,
    messages: Sequence[BaseMessage],
    runtime_snapshot: bool = False,
) -> Mapping[str, object] | None:
    runtime_metadata = runtime_rag_context_metadata(messages)
    if runtime_metadata is None:
        return context_manifest
    manifest = dict(context_manifest or {})
    raw_sections = manifest.get("sections")
    sections = (
        [
            dict(cast(Mapping[str, object], section))
            for section in cast(Sequence[object], raw_sections)
            if isinstance(section, Mapping)
        ]
        if isinstance(raw_sections, Sequence)
        and not isinstance(raw_sections, str | bytes | bytearray)
        else []
    )
    rag_section = next(
        (section for section in sections if section.get("name") == "rag_context"), None
    )
    existing_metadata = (
        safe_manifest_metadata(cast(Mapping[str, object], rag_section.get("metadata", {})))
        if rag_section is not None and isinstance(rag_section.get("metadata"), Mapping)
        else {}
    )
    existing_citations = mapping_sequence(existing_metadata.get("citations"))
    runtime_citations = mapping_sequence(runtime_metadata.get("citations"))
    citations_by_id: dict[str, dict[str, object]] = {}
    citations_without_id: list[dict[str, object]] = []
    for citation in [*existing_citations, *runtime_citations]:
        bounded = bounded_citation_evidence(citation)
        citation_id = bounded.get("citation_id")
        if isinstance(citation_id, str):
            citations_by_id[citation_id] = bounded
        elif bounded:
            citations_without_id.append(bounded)
    citations = [*citations_by_id.values(), *citations_without_id]
    chunk_count, runtime_chunk_count = merge_runtime_evidence_count(
        existing_metadata,
        runtime_metadata,
        total_key="chunk_count",
        runtime_key="runtime_chunk_count",
        runtime_snapshot=runtime_snapshot,
    )
    cited_chunk_count, runtime_cited_chunk_count = merge_runtime_evidence_count(
        existing_metadata,
        runtime_metadata,
        total_key="cited_chunk_count",
        runtime_key="runtime_cited_chunk_count",
        runtime_snapshot=runtime_snapshot,
    )
    merged_metadata: dict[str, object] = {
        **existing_metadata,
        "ragGroundingPolicy": dict(RAG_GROUNDING_POLICY),
        "chunk_count": chunk_count,
        "cited_chunk_count": cited_chunk_count,
        "uncited_chunk_count": max(0, chunk_count - cited_chunk_count),
        "citation_count": len(citations),
        "citations": citations,
    }
    if runtime_chunk_count:
        merged_metadata["runtime_chunk_count"] = runtime_chunk_count
    if runtime_cited_chunk_count:
        merged_metadata["runtime_cited_chunk_count"] = runtime_cited_chunk_count
    invalid_citation_id_count, runtime_invalid_citation_id_count = merge_runtime_evidence_count(
        existing_metadata,
        runtime_metadata,
        total_key="invalid_citation_id_count",
        runtime_key="runtime_invalid_citation_id_count",
        runtime_snapshot=runtime_snapshot,
    )
    if invalid_citation_id_count:
        merged_metadata["invalid_citation_id_count"] = invalid_citation_id_count
    if runtime_invalid_citation_id_count:
        merged_metadata["runtime_invalid_citation_id_count"] = runtime_invalid_citation_id_count
    orphan_citation_id_count, runtime_orphan_citation_id_count = merge_runtime_evidence_count(
        existing_metadata,
        runtime_metadata,
        total_key="orphan_citation_id_count",
        runtime_key="runtime_orphan_citation_id_count",
        runtime_snapshot=runtime_snapshot,
    )
    if orphan_citation_id_count:
        merged_metadata["orphan_citation_id_count"] = orphan_citation_id_count
    if runtime_orphan_citation_id_count:
        merged_metadata["runtime_orphan_citation_id_count"] = runtime_orphan_citation_id_count
    duplicate_citation_id_count, runtime_duplicate_citation_id_count = merge_runtime_evidence_count(
        existing_metadata,
        runtime_metadata,
        total_key="duplicate_citation_id_count",
        runtime_key="runtime_duplicate_citation_id_count",
        runtime_snapshot=runtime_snapshot,
    )
    if duplicate_citation_id_count:
        merged_metadata["duplicate_citation_id_count"] = duplicate_citation_id_count
    if runtime_duplicate_citation_id_count:
        merged_metadata["runtime_duplicate_citation_id_count"] = runtime_duplicate_citation_id_count
    citation_metadata_mismatch_count, runtime_citation_metadata_mismatch_count = (
        merge_runtime_evidence_count(
            existing_metadata,
            runtime_metadata,
            total_key="citation_metadata_mismatch_count",
            runtime_key="runtime_citation_metadata_mismatch_count",
            runtime_snapshot=runtime_snapshot,
        )
    )
    if citation_metadata_mismatch_count:
        merged_metadata["citation_metadata_mismatch_count"] = citation_metadata_mismatch_count
    if runtime_citation_metadata_mismatch_count:
        merged_metadata["runtime_citation_metadata_mismatch_count"] = (
            runtime_citation_metadata_mismatch_count
        )
    duplicate_chunk_citation_id_count, runtime_duplicate_chunk_citation_id_count = (
        merge_runtime_evidence_count(
            existing_metadata,
            runtime_metadata,
            total_key="duplicate_chunk_citation_id_count",
            runtime_key="runtime_duplicate_chunk_citation_id_count",
            runtime_snapshot=runtime_snapshot,
        )
    )
    if duplicate_chunk_citation_id_count:
        merged_metadata["duplicate_chunk_citation_id_count"] = duplicate_chunk_citation_id_count
    if runtime_duplicate_chunk_citation_id_count:
        merged_metadata["runtime_duplicate_chunk_citation_id_count"] = (
            runtime_duplicate_chunk_citation_id_count
        )
    invalid_chunk_citation_id_count, runtime_invalid_chunk_citation_id_count = (
        merge_runtime_evidence_count(
            existing_metadata,
            runtime_metadata,
            total_key="invalid_chunk_citation_id_count",
            runtime_key="runtime_invalid_chunk_citation_id_count",
            runtime_snapshot=runtime_snapshot,
        )
    )
    if invalid_chunk_citation_id_count:
        merged_metadata["invalid_chunk_citation_id_count"] = invalid_chunk_citation_id_count
    if runtime_invalid_chunk_citation_id_count:
        merged_metadata["runtime_invalid_chunk_citation_id_count"] = (
            runtime_invalid_chunk_citation_id_count
        )
    omitted_citation_count, runtime_omitted_citation_count = merge_runtime_evidence_count(
        existing_metadata,
        runtime_metadata,
        total_key="omitted_citation_count",
        runtime_key="runtime_omitted_citation_count",
        runtime_snapshot=runtime_snapshot,
    )
    if omitted_citation_count:
        merged_metadata["omitted_citation_count"] = omitted_citation_count
    if runtime_omitted_citation_count:
        merged_metadata["runtime_omitted_citation_count"] = runtime_omitted_citation_count
    invalid_runtime_rag_artifact_count, runtime_invalid_rag_artifact_count = (
        merge_runtime_evidence_count(
            existing_metadata,
            runtime_metadata,
            total_key="invalid_runtime_rag_artifact_count",
            runtime_key="runtime_invalid_rag_artifact_count",
            runtime_snapshot=runtime_snapshot,
        )
    )
    if invalid_runtime_rag_artifact_count:
        merged_metadata["invalid_runtime_rag_artifact_count"] = invalid_runtime_rag_artifact_count
    if runtime_invalid_rag_artifact_count:
        merged_metadata["runtime_invalid_rag_artifact_count"] = runtime_invalid_rag_artifact_count
    if citations:
        first = citations[0]
        for key in (
            "citation_id",
            "source_uri",
            "document_id",
            "chunk_index",
            "content_hash",
            "acl_hash",
        ):
            if key in first:
                merged_metadata[key] = first[key]
    if rag_section is None:
        rag_section = ContextSection(
            name="rag_context",
            content="none",
            source_type="rag",
            tainted=True,
            metadata=merged_metadata,
        ).manifest_entry()
        sections.append(rag_section)
    else:
        rag_section["metadata"] = safe_manifest_metadata(merged_metadata)
    sections.sort(
        key=lambda section: CONTEXT_SECTION_RANK.get(
            str(section.get("name", "")),
            len(CONTEXT_SECTION_RANK),
        )
    )
    manifest["sections"] = sections
    return manifest


def runtime_rag_context_metadata(
    messages: Sequence[BaseMessage],
) -> dict[str, object] | None:
    metadata_items: list[Mapping[str, object]] = []
    invalid_artifact_count = 0
    for message in messages:
        if not isinstance(message, ToolMessage):
            continue
        if isinstance(message.artifact, Mapping):
            artifact = cast(Mapping[str, object], message.artifact)
            metadata = artifact.get("rag_context_manifest")
            if artifact.get("tool_id") == "Rag:hybrid_search" and isinstance(metadata, Mapping):
                recognized, valid, durable_metadata = durable_rag_context_metadata(message)
                if (
                    not valid_reactor_rag_artifact(artifact)
                    or artifact.get("model_visible_text") != message.content
                    or not recognized
                    or not valid
                    or durable_metadata is None
                    or not rag_artifact_manifest_matches_durable(
                        cast(Mapping[str, object], metadata),
                        durable_metadata,
                    )
                ):
                    invalid_artifact_count += 1
                    continue
                metadata_items.append(cast(Mapping[str, object], metadata))
                continue
        recognized, valid, durable_metadata = durable_rag_context_metadata(message)
        if not recognized:
            continue
        if not valid:
            invalid_artifact_count += 1
            continue
        if durable_metadata is not None:
            metadata_items.append(durable_metadata)
    if not metadata_items and not invalid_artifact_count:
        return None
    citations = [
        bounded_citation_evidence(citation)
        for metadata in metadata_items
        for citation in mapping_sequence(metadata.get("citations"))
    ]
    return {
        "chunk_count": sum(
            non_negative_int_value(item.get("chunk_count")) for item in metadata_items
        ),
        "cited_chunk_count": sum(
            non_negative_int_value(item.get("cited_chunk_count")) for item in metadata_items
        ),
        "citations": [citation for citation in citations if citation],
        "invalid_citation_id_count": sum(
            non_negative_int_value(item.get("invalid_citation_id_count")) for item in metadata_items
        ),
        "orphan_citation_id_count": sum(
            non_negative_int_value(item.get("orphan_citation_id_count")) for item in metadata_items
        ),
        "duplicate_citation_id_count": sum(
            non_negative_int_value(item.get("duplicate_citation_id_count"))
            for item in metadata_items
        ),
        "citation_metadata_mismatch_count": sum(
            non_negative_int_value(item.get("citation_metadata_mismatch_count"))
            for item in metadata_items
        ),
        "duplicate_chunk_citation_id_count": sum(
            non_negative_int_value(item.get("duplicate_chunk_citation_id_count"))
            for item in metadata_items
        ),
        "invalid_chunk_citation_id_count": sum(
            non_negative_int_value(item.get("invalid_chunk_citation_id_count"))
            for item in metadata_items
        ),
        "omitted_citation_count": sum(
            non_negative_int_value(item.get("omitted_citation_count")) for item in metadata_items
        ),
        "invalid_runtime_rag_artifact_count": invalid_artifact_count,
    }


def valid_reactor_rag_artifact(artifact: Mapping[str, object]) -> bool:
    idempotency_key = artifact.get("idempotency_key")
    model_visible_text = artifact.get("model_visible_text")
    sanitizer_findings = artifact.get("sanitizer_findings")
    return (
        artifact.get("schema") == REACTOR_TOOL_ARTIFACT_SCHEMA
        and artifact.get("status") == "succeeded"
        and artifact.get("tool_id") == "Rag:hybrid_search"
        and isinstance(idempotency_key, str)
        and bool(idempotency_key.strip())
        and isinstance(model_visible_text, str)
        and model_visible_text.startswith("[tool_output:data]\n")
        and isinstance(sanitizer_findings, Sequence)
        and not isinstance(sanitizer_findings, str | bytes | bytearray)
        and all(
            isinstance(finding, str) and finding in TOOL_OUTPUT_SANITIZER_FINDINGS
            for finding in cast(Sequence[object], sanitizer_findings)
        )
    )


def rag_artifact_manifest_matches_durable(
    artifact_metadata: Mapping[str, object],
    durable_metadata: Mapping[str, object],
) -> bool:
    count_fields = (
        "chunk_count",
        "cited_chunk_count",
        "uncited_chunk_count",
        "citation_count",
        "invalid_citation_id_count",
        "orphan_citation_id_count",
        "duplicate_citation_id_count",
        "citation_metadata_mismatch_count",
        "duplicate_chunk_citation_id_count",
        "invalid_chunk_citation_id_count",
        "omitted_citation_count",
    )
    if any(
        non_negative_int_value(artifact_metadata.get(field))
        != non_negative_int_value(durable_metadata.get(field))
        for field in count_fields
    ):
        return False
    artifact_citations = mapping_sequence(artifact_metadata.get("citations"))
    durable_citations = mapping_sequence(durable_metadata.get("citations"))
    if len(artifact_citations) != len(durable_citations):
        return False
    return all(
        all(artifact_citation.get(key) == value for key, value in durable_citation.items())
        for artifact_citation, durable_citation in zip(
            artifact_citations,
            durable_citations,
            strict=True,
        )
    )


def durable_rag_context_metadata(
    message: ToolMessage,
) -> tuple[bool, bool, Mapping[str, object] | None]:
    is_named_rag = message.name == "Rag:hybrid_search"
    content = message.content
    if not isinstance(content, str) or not content.startswith("[tool_output:data]\n"):
        return is_named_rag, False, None
    try:
        decoded = json.loads(content.removeprefix("[tool_output:data]\n"))
    except json.JSONDecodeError:
        return is_named_rag, False, None
    if not isinstance(decoded, Mapping):
        return is_named_rag, False, None
    envelope = cast(Mapping[str, object], decoded)
    if envelope.get("tool_id") != "Rag:hybrid_search":
        return is_named_rag, False, None
    idempotency_key = envelope.get("idempotency_key")
    payload = envelope.get("payload")
    if (
        envelope.get("schema") != REACTOR_TOOL_ARTIFACT_SCHEMA
        or envelope.get("status") != "succeeded"
        or not isinstance(idempotency_key, str)
        or not idempotency_key.strip()
        or not isinstance(payload, Mapping)
    ):
        return True, False, None
    metadata = rag_context_manifest_metadata_from_payload(cast(Mapping[str, object], payload))
    return True, True, metadata


def mapping_sequence(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return []
    return [
        cast(Mapping[str, object], item)
        for item in cast(Sequence[object], value)
        if isinstance(item, Mapping)
    ]


def non_negative_int_value(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def merge_runtime_evidence_count(
    existing_metadata: Mapping[str, object],
    runtime_metadata: Mapping[str, object],
    *,
    total_key: str,
    runtime_key: str,
    runtime_snapshot: bool,
) -> tuple[int, int]:
    existing_total = non_negative_int_value(existing_metadata.get(total_key))
    previous_runtime = non_negative_int_value(existing_metadata.get(runtime_key))
    current_runtime = non_negative_int_value(runtime_metadata.get(total_key))
    base_total = max(0, existing_total - previous_runtime)
    merged_runtime = current_runtime if runtime_snapshot else previous_runtime + current_runtime
    return base_total + merged_runtime, merged_runtime


def context_manifest_with_tool_output_guard(
    context_manifest: Mapping[str, object] | None,
    *,
    metadata: Mapping[str, object],
    model_visible_outputs: Sequence[str],
) -> dict[str, object]:
    manifest = dict(context_manifest or {})
    raw_sections = manifest.get("sections")
    sections = (
        [
            dict(cast(Mapping[str, object], section))
            for section in cast(Sequence[object], raw_sections)
            if isinstance(section, Mapping) and section.get("name") != "tool_outputs"
        ]
        if isinstance(raw_sections, Sequence)
        and not isinstance(raw_sections, str | bytes | bytearray)
        else []
    )
    tool_output_section = ContextSection(
        name="tool_outputs",
        content="\n".join(model_visible_outputs),
        source_type="tool",
        tainted=True,
        metadata=metadata,
    ).manifest_entry()
    sections.append(tool_output_section)
    sections.sort(
        key=lambda section: CONTEXT_SECTION_RANK.get(
            str(section.get("name", "")),
            len(CONTEXT_SECTION_RANK),
        )
    )
    manifest["sections"] = sections
    return manifest


def graph_output_value(result: object) -> object:
    if hasattr(result, "value"):
        return cast(Any, result).value
    return result


def graph_output_interrupts(result: object) -> tuple[object, ...]:
    raw_interrupts = getattr(result, "interrupts", None)
    if isinstance(raw_interrupts, Sequence) and not isinstance(
        raw_interrupts,
        str | bytes | bytearray,
    ):
        return tuple(cast(Sequence[object], raw_interrupts))
    if isinstance(result, Mapping):
        legacy_interrupts = cast(Mapping[object, object], result).get("__interrupt__")
        if isinstance(legacy_interrupts, Sequence) and not isinstance(
            legacy_interrupts,
            str | bytes | bytearray,
        ):
            return tuple(cast(Sequence[object], legacy_interrupts))
    return ()


def extract_langchain_interrupt_actions(
    result_or_interrupts: object,
) -> tuple[LangChainInterruptAction, ...]:
    interrupts = (
        tuple(cast(Sequence[object], result_or_interrupts))
        if isinstance(result_or_interrupts, Sequence)
        and not isinstance(result_or_interrupts, str | bytes | bytearray)
        else graph_output_interrupts(result_or_interrupts)
    )
    actions: list[LangChainInterruptAction] = []
    for interrupt in interrupts:
        value = getattr(interrupt, "value", interrupt)
        if not isinstance(value, Mapping):
            return ()
        raw_actions = cast(Mapping[object, object], value).get("action_requests")
        if not isinstance(raw_actions, Sequence) or isinstance(
            raw_actions,
            str | bytes | bytearray,
        ):
            return ()
        if not raw_actions:
            return ()
        for raw_action in cast(Sequence[object], raw_actions):
            if not isinstance(raw_action, Mapping):
                return ()
            action_mapping = cast(Mapping[object, object], raw_action)
            tool_name = action_mapping.get("name")
            arguments = action_mapping.get("args")
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


def extract_structured_response(
    result: object,
    *,
    structured_output_schema: object | None = None,
) -> str | None:
    if not isinstance(result, dict) or "structured_response" not in result:
        return None
    try:
        structured_response = cast(object, result["structured_response"])
        if isinstance(structured_response, str):
            if structured_output_schema_allows_string_scalar(structured_output_schema):
                return json.dumps(structured_response, ensure_ascii=False, separators=(",", ":"))
            return structured_response
        if hasattr(structured_response, "model_dump"):
            structured_response = cast(Any, structured_response).model_dump(mode="json")
        elif is_dataclass(structured_response) and not isinstance(structured_response, type):
            structured_response = asdict(structured_response)
        return json.dumps(structured_response, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        return _STRUCTURED_RESPONSE_SERIALIZATION_FAILURE


def structured_output_schema_allows_string_scalar(schema: object | None) -> bool:
    if not isinstance(schema, Mapping):
        return False
    schema_mapping = cast(Mapping[str, object], schema)
    schema_type = schema_mapping.get("type")
    if schema_type == "string":
        return True
    if isinstance(schema_type, Sequence) and not isinstance(schema_type, str | bytes | bytearray):
        return "string" in schema_type
    return False


async def enforce_structured_response_boundary(
    response: str,
    *,
    response_format: str | None,
    structured_output_schema: object | None,
    context_manifest: Mapping[str, object] | None = None,
    repairer: StructuredResponseRepairer | None = None,
) -> str:
    return (
        await enforce_structured_response_boundary_with_metadata(
            response,
            response_format=response_format,
            structured_output_schema=structured_output_schema,
            context_manifest=context_manifest,
            repairer=repairer,
        )
    ).response


async def enforce_structured_response_boundary_with_metadata(
    response: str,
    *,
    response_format: str | None,
    structured_output_schema: object | None,
    context_manifest: Mapping[str, object] | None = None,
    repairer: StructuredResponseRepairer | None = None,
) -> StructuredBoundaryResult:
    if response == _STRUCTURED_RESPONSE_SERIALIZATION_FAILURE:
        return StructuredBoundaryResult(
            response="Response blocked by structured output policy.",
            metadata={
                "structured_output_status": "invalid",
                "structured_output_error_code": "STRUCTURED_RESPONSE_SERIALIZATION_FAILED",
                "stop_reason": "structured_output_invalid",
            },
        )
    actual_format = (
        ResponseFormat.JSON
        if structured_output_schema is not None
        else extract_response_format(response_format)
    )
    if actual_format == ResponseFormat.TEXT:
        return StructuredBoundaryResult(response=response)
    actual_repairer = repairer or StructuredResponseRepairer()
    citation_ids = context_manifest_citation_ids(context_manifest)
    unsafe_citation_count = context_manifest_unsafe_citation_count(context_manifest)
    citation_metadata = structured_output_citation_metadata(
        context_manifest=context_manifest,
        response_format=actual_format,
        citation_count=len(citation_ids),
    )
    response_schema = merge_citation_response_schema(
        structured_output_schema_mapping(structured_output_schema),
        context_manifest,
    )
    if (
        citation_metadata
        and context_manifest_requires_citations(context_manifest)
        and unsafe_citation_count
    ):
        return StructuredBoundaryResult(
            response="Response blocked by structured output policy.",
            metadata={
                "structured_output_status": "invalid",
                "structured_output_error_code": "UNSAFE_CONTEXT_CITATION_IDS",
                "stop_reason": "structured_output_invalid",
                **citation_metadata,
            },
        )
    if (
        citation_metadata
        and context_manifest_requires_citations(context_manifest)
        and not citation_ids
    ):
        return StructuredBoundaryResult(
            response="Response blocked by structured output policy.",
            metadata={
                "structured_output_status": "invalid",
                "structured_output_error_code": "MISSING_CONTEXT_CITATIONS",
                "stop_reason": "structured_output_invalid",
                **citation_metadata,
            },
        )
    result = await actual_repairer.validate_and_repair(
        response,
        actual_format,
        schema=response_schema,
    )
    if result.success and result.content is not None:
        return StructuredBoundaryResult(
            response=result.content,
            metadata={
                "structured_output_status": "valid" if result.content == response else "repaired",
                **citation_metadata,
            },
        )
    return StructuredBoundaryResult(
        response="Response blocked by structured output policy.",
        metadata={
            "structured_output_status": "invalid",
            "structured_output_error_code": result.error_code or "INVALID_RESPONSE",
            "stop_reason": "structured_output_invalid",
            **citation_metadata,
        },
    )


def structured_output_citation_metadata(
    *,
    context_manifest: Mapping[str, object] | None,
    response_format: ResponseFormat,
    citation_count: int,
) -> dict[str, object]:
    if (
        not context_manifest_requires_citations(context_manifest)
        or response_format != ResponseFormat.JSON
    ):
        return {}
    unsafe_citation_count = context_manifest_unsafe_citation_count(context_manifest)
    unsafe_metadata = (
        {"structured_output_unsafe_citation_count": unsafe_citation_count}
        if unsafe_citation_count
        else {}
    )
    return {
        "structured_output_citation_policy": "required",
        "structured_output_citation_count": citation_count,
        "structured_output_allowed_citation_ids": context_manifest_citation_ids(context_manifest),
        **unsafe_metadata,
    }


def structured_output_schema_mapping(schema: object | None) -> Mapping[str, object] | None:
    if isinstance(schema, Mapping):
        return cast(Mapping[str, object], schema)
    return None


def extract_response_text(messages: Sequence[BaseMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            return message.text
    return ""


def latest_provider_usage(
    messages: list[BaseMessage],
    *,
    max_output_tokens: int,
) -> TokenUsage | None:
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            usage = usage_from_provider_metadata(
                message,
                max_output_tokens=max_output_tokens,
            )
            if usage is not None:
                return usage
    return None
