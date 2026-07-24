from __future__ import annotations

from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from reactor.agents.tool_state import (
    normalize_pending_tool_request_update,
    normalize_pending_tool_requests_update,
)

REACTOR_STATE_SCHEMA_VERSION = "reactor.agent.state.v1"


class StateSchemaVersionError(ValueError):
    pass


def require_current_state_schema(state: ReactorState) -> str:
    version = state.get("state_schema_version")
    if version != REACTOR_STATE_SCHEMA_VERSION:
        rendered = "missing" if version is None else repr(version)
        raise StateSchemaVersionError(
            "unsupported reactor state_schema_version: "
            f"{rendered}; expected {REACTOR_STATE_SCHEMA_VERSION!r}"
        )
    return version


class ReactorState(TypedDict, total=False):
    state_schema_version: str
    run_id: str
    user_id: str
    tenant_id: str
    trusted_user_groups: tuple[str, ...] | list[str]
    messages: Annotated[list[AnyMessage], add_messages]
    response_text: str
    response_format: str
    response_schema: dict[str, object]
    response_metadata: dict[str, object]
    request_system_prompt: str
    rendered_system_prompt: str
    integration_context: dict[str, object]
    session_memory: list[object]
    rag_context: list[str]
    tool_call_count: int
    max_tool_calls: int
    active_tools: list[str]
    active_tool_specs: list[dict[str, object]]
    tool_profile_budget: dict[str, object]
    tool_profile_budget_metadata: dict[str, object]
    graph_profile: str
    prompt_version: str
    profile_checkpoint_ns: str
    selected_model: str
    model_provider: str
    temperature: float
    node_sequence: list[str]
    guard_status: str
    context_manifest: dict[str, object]
    research_plan: dict[str, object]
    approval_status: str
    approval_resume: dict[str, object]
    pending_tool_request: Annotated[
        dict[str, object],
        normalize_pending_tool_request_update,
    ]
    pending_tool_requests: Annotated[
        list[dict[str, object]],
        normalize_pending_tool_requests_update,
    ]
    tool_results: list[dict[str, object]]
    output_guard_status: str
