from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any, cast

from langchain_core.messages import AnyMessage
from langchain_core.runnables import RunnableConfig

from reactor.agents.state import REACTOR_STATE_SCHEMA_VERSION, ReactorState

DEFAULT_LANGGRAPH_RECURSION_LIMIT = 25
LANGGRAPH_ROOT_CHECKPOINT_NS = ""
LANGGRAPH_CHECKPOINT_SCOPE_VERSION = "v1"
LANGGRAPH_NATIVE_INVOKE_RUN_NAME = "reactor.langgraph.invoke"
LANGGRAPH_NATIVE_STREAM_RUN_NAME = "reactor.langgraph.stream"
LANGGRAPH_NATIVE_RESUME_RUN_NAME = "reactor.langgraph.resume"
LANGGRAPH_NATIVE_RUN_TAGS = ("reactor", "runtime:langgraph")
LANGGRAPH_NATIVE_CONFIG_METADATA = {"reactor.runtime": "langgraph"}


def initial_reactor_state(
    *,
    run_id: str,
    tenant_id: str,
    user_id: str,
    trusted_user_groups: tuple[str, ...],
    messages: list[AnyMessage],
    max_tool_calls: int | None,
    checkpoint_ns: str,
    request_system_prompt: str | None = None,
    model_provider: str | None = None,
    selected_model: str | None = None,
    graph_profile: str | None = None,
    integration_context: dict[str, object] | None = None,
    active_tools: list[str] | None = None,
    active_tool_specs: list[dict[str, object]] | None = None,
) -> ReactorState:
    state = ReactorState(
        {
            "state_schema_version": REACTOR_STATE_SCHEMA_VERSION,
            "run_id": run_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "trusted_user_groups": trusted_user_groups,
            "messages": messages,
            "tool_call_count": 0,
        }
    )
    if not checkpoint_ns.strip():
        raise ValueError("checkpoint_ns is required")
    state["profile_checkpoint_ns"] = checkpoint_ns.strip()
    if max_tool_calls is not None:
        state["max_tool_calls"] = max_tool_calls
    if request_system_prompt is not None and request_system_prompt.strip():
        state["request_system_prompt"] = request_system_prompt.strip()
    if model_provider is not None and model_provider.strip():
        state["model_provider"] = model_provider.strip()
    if selected_model is not None and selected_model.strip():
        state["selected_model"] = selected_model.strip()
    if graph_profile is not None and graph_profile.strip():
        state["graph_profile"] = graph_profile.strip()
    if integration_context:
        state["integration_context"] = dict(integration_context)
    if active_tools is not None:
        state["active_tools"] = list(active_tools)
    if active_tool_specs is not None:
        state["active_tool_specs"] = [dict(spec) for spec in active_tool_specs]
    return state


def langgraph_durable_config(
    *,
    tenant_id: str,
    thread_id: str,
    checkpoint_ns: str,
    checkpoint_id: str | None = None,
    recursion_limit: int = DEFAULT_LANGGRAPH_RECURSION_LIMIT,
    run_name: str | None = None,
    tags: Sequence[str] = (),
    metadata: Mapping[str, Any] | None = None,
) -> RunnableConfig:
    checkpoint_thread_id = langgraph_checkpoint_thread_id(
        tenant_id=tenant_id,
        thread_id=thread_id,
        checkpoint_ns=checkpoint_ns,
    )
    if isinstance(recursion_limit, bool) or recursion_limit <= 0:
        raise ValueError("recursion_limit must be greater than 0")
    configurable = {
        "thread_id": checkpoint_thread_id,
        "checkpoint_ns": LANGGRAPH_ROOT_CHECKPOINT_NS,
    }
    if checkpoint_id is not None:
        configurable["checkpoint_id"] = require_nonblank("checkpoint_id", checkpoint_id)
    config: dict[str, object] = {
        "recursion_limit": recursion_limit,
        "configurable": configurable,
    }
    if run_name is not None:
        config["run_name"] = require_nonblank("run_name", run_name)
    if tags:
        config["tags"] = [require_nonblank("tag", tag) for tag in tags]
    if metadata:
        config["metadata"] = dict(metadata)
    return cast(
        RunnableConfig,
        config,
    )


def langgraph_checkpoint_thread_id(
    *,
    tenant_id: str,
    thread_id: str,
    checkpoint_ns: str,
) -> str:
    """Map Reactor's logical checkpoint scope onto LangGraph's root thread key.

    LangGraph reserves ``checkpoint_ns`` for subgraph paths and resets it to the
    empty string for root graph executions. Reactor therefore scopes the physical
    root thread by tenant, logical thread, and product checkpoint namespace.
    """
    identity = [
        require_nonblank("tenant_id", tenant_id),
        require_nonblank("thread_id", thread_id),
        require_nonblank("checkpoint_ns", checkpoint_ns),
    ]
    payload = json.dumps(identity, ensure_ascii=False, separators=(",", ":")).encode()
    digest = hashlib.sha256(payload).hexdigest()
    return f"reactor:checkpoint:{LANGGRAPH_CHECKPOINT_SCOPE_VERSION}:{digest}"


def require_nonblank(name: str, value: str) -> str:
    clean_value = value.strip()
    if not clean_value:
        raise ValueError(f"{name} must not be blank")
    return clean_value
