from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from langgraph.types import Command

from reactor.agents.interrupts import approval_resume_to_state_payload
from reactor.agents.state import REACTOR_STATE_SCHEMA_VERSION, StateSchemaVersionError
from reactor.agents.tool_state import pending_tool_request_to_state_payload


class JsonSafeReactorGraph:
    """Normalize checkpoint-bound product state before LangGraph sees the input."""

    def __init__(self, graph: Any) -> None:
        self._graph = graph

    def __getattr__(self, name: str) -> Any:
        return getattr(self._graph, name)

    def invoke(self, input: object, *args: Any, **kwargs: Any) -> Any:
        del input, args, kwargs
        raise RuntimeError("synchronous graph invocation is forbidden; use ainvoke")

    async def ainvoke(self, input: object, *args: Any, **kwargs: Any) -> Any:
        return await self._graph.ainvoke(normalize_reactor_graph_input(input), *args, **kwargs)

    def stream(self, input: object, *args: Any, **kwargs: Any) -> Any:
        del input, args, kwargs
        raise RuntimeError("synchronous graph streaming is forbidden; use astream")

    def astream(self, input: object, *args: Any, **kwargs: Any) -> Any:
        return self._graph.astream(normalize_reactor_graph_input(input), *args, **kwargs)

    def astream_events(self, input: object, *args: Any, **kwargs: Any) -> Any:
        return self._graph.astream_events(
            normalize_reactor_graph_input(input),
            *args,
            **kwargs,
        )

    def with_config(self, *args: Any, **kwargs: Any) -> JsonSafeReactorGraph:
        return JsonSafeReactorGraph(self._graph.with_config(*args, **kwargs))


def normalize_reactor_graph_input(input: object) -> object:
    if isinstance(input, Command):
        if input.graph is not None or input.update is not None or input.goto:
            raise ValueError("external resume Command may only contain resume")
        return Command(resume=approval_resume_to_state_payload(input.resume))
    if not isinstance(input, Mapping):
        return input
    normalized = dict(cast(Mapping[str, object], input))
    state_schema_version = normalized.get("state_schema_version")
    if state_schema_version is None:
        normalized["state_schema_version"] = REACTOR_STATE_SCHEMA_VERSION
    elif state_schema_version != REACTOR_STATE_SCHEMA_VERSION:
        raise StateSchemaVersionError(
            "unsupported reactor state_schema_version: "
            f"{state_schema_version!r}; expected {REACTOR_STATE_SCHEMA_VERSION!r}"
        )
    pending_tool = normalized.get("pending_tool_request")
    if pending_tool:
        if not isinstance(pending_tool, Mapping):
            raise ValueError("pending_tool_request must be an object")
        normalized["pending_tool_request"] = pending_tool_request_to_state_payload(
            cast(Mapping[str, object], pending_tool)
        )
    pending_tools = normalized.get("pending_tool_requests")
    if pending_tools is not None:
        if not isinstance(pending_tools, list):
            raise ValueError("pending_tool_requests must be a list")
        normalized["pending_tool_requests"] = [
            pending_tool_request_to_state_payload(cast(Mapping[str, object], item))
            if isinstance(item, Mapping)
            else _raise_invalid_pending_tool_request()
            for item in cast(list[object], pending_tools)
        ]
    return normalized


def _raise_invalid_pending_tool_request() -> dict[str, object]:
    raise ValueError("pending_tool_requests items must be objects")
