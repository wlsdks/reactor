from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from reactor.agents.events import AgentStreamEvent
from reactor.persistence.run_store import RunEventRecord

LANGCHAIN_RAW_STREAM_EVENTS_VERSION = "v2"
LANGGRAPH_INTERRUPT_STREAM_EVENTS_VERSION = "v2"
LANGCHAIN_AGENT_STREAM_EVENTS_VERSION = "v2"


def replay_stream_events(
    events: list[RunEventRecord],
    *,
    after_sequence: int = 0,
) -> list[RunEventRecord]:
    return [
        event
        for event in events
        if event.sequence > after_sequence and event.event_type.startswith("run.stream.")
    ]


def stream_started_event(run_id: str, trace_id: str) -> AgentStreamEvent:
    return AgentStreamEvent(
        run_id=run_id,
        sequence=2,
        event_type="run.stream.started",
        graph_node="guard",
        trace_id=trace_id,
    )


def langgraph_stream_event_to_agent_event(
    raw_event: Mapping[str, object],
    *,
    run_id: str,
    sequence: int,
    fallback_trace_id: str,
) -> AgentStreamEvent | None:
    interrupts = langchain_v2_stream_interrupts(raw_event)
    if interrupts:
        return AgentStreamEvent(
            run_id=run_id,
            sequence=sequence,
            event_type="run.stream.approval",
            graph_node="approval_gate",
            trace_id=fallback_trace_id,
            payload={
                "approval_status": "pending",
                "action_count": native_langgraph_stream_action_count(interrupts),
            },
        )
    event_type = raw_event.get("event")
    if event_type not in {"on_chain_stream", "on_chat_model_stream"}:
        return None
    metadata = raw_event.get("metadata")
    if not isinstance(metadata, dict):
        return None
    typed_metadata = cast(dict[object, object], metadata)
    graph_node = typed_metadata.get("langgraph_node")
    if not isinstance(graph_node, str) or not graph_node.strip():
        return None
    chunk = langgraph_stream_chunk(raw_event)
    if chunk is None:
        return None
    trace_id = langgraph_trace_id(raw_event, fallback_trace_id)
    text = stream_chunk_text(chunk)
    if isinstance(text, str) and text:
        return AgentStreamEvent(
            run_id=run_id,
            sequence=sequence,
            event_type="run.stream.token",
            graph_node=graph_node,
            trace_id=trace_id,
            payload={"text": text},
        )
    if not isinstance(chunk, Mapping):
        return None
    typed_chunk = cast(Mapping[object, object], chunk)
    tool_results = typed_chunk.get("tool_results")
    if isinstance(tool_results, list) and tool_results:
        return AgentStreamEvent(
            run_id=run_id,
            sequence=sequence,
            event_type="run.stream.tool",
            graph_node=graph_node,
            trace_id=trace_id,
            payload={"tool_results": tool_results},
        )
    return None


def langchain_v2_stream_event_to_agent_event(
    raw_event: Mapping[str, object],
    *,
    run_id: str,
    sequence: int,
    fallback_trace_id: str,
) -> AgentStreamEvent | None:
    interrupts = langchain_v2_stream_interrupts(raw_event)
    if interrupts:
        action_count = langchain_stream_action_count(interrupts)
        return AgentStreamEvent(
            run_id=run_id,
            sequence=sequence,
            event_type="run.stream.approval",
            graph_node="approval_gate",
            trace_id=fallback_trace_id,
            payload={
                "approval_status": "pending",
                "action_count": action_count,
            },
        )
    return langgraph_stream_event_to_agent_event(
        raw_event,
        run_id=run_id,
        sequence=sequence,
        fallback_trace_id=fallback_trace_id,
    )


def langchain_v2_stream_interrupts(raw_event: Mapping[str, object]) -> tuple[object, ...]:
    if raw_event.get("event") != "on_chain_stream":
        return ()
    parent_ids = raw_event.get("parent_ids")
    if (
        not isinstance(parent_ids, Sequence)
        or isinstance(parent_ids, str | bytes | bytearray)
        or parent_ids
    ):
        return ()
    chunk = langgraph_stream_chunk(raw_event)
    if not isinstance(chunk, Mapping):
        return ()
    raw_interrupts = cast(Mapping[object, object], chunk).get("__interrupt__")
    if not isinstance(raw_interrupts, Sequence) or isinstance(
        raw_interrupts,
        str | bytes | bytearray,
    ):
        return ()
    return tuple(cast(Sequence[object], raw_interrupts))


def langchain_v2_stream_interrupt_lineage_invalid(
    raw_event: Mapping[str, object],
) -> bool:
    if raw_event.get("event") != "on_chain_stream":
        return False
    chunk = langgraph_stream_chunk(raw_event)
    if not isinstance(chunk, Mapping) or "__interrupt__" not in chunk:
        return False
    parent_ids = raw_event.get("parent_ids")
    if not isinstance(parent_ids, Sequence) or isinstance(
        parent_ids,
        str | bytes | bytearray,
    ):
        return True
    return len(cast(Sequence[object], parent_ids)) != 0


def langchain_v2_stream_interrupt_payload_invalid(
    raw_event: Mapping[str, object],
) -> bool:
    if raw_event.get("event") != "on_chain_stream":
        return False
    chunk = langgraph_stream_chunk(raw_event)
    if not isinstance(chunk, Mapping) or "__interrupt__" not in chunk:
        return False
    raw_interrupts = cast(Mapping[object, object], chunk).get("__interrupt__")
    if not isinstance(raw_interrupts, Sequence) or isinstance(
        raw_interrupts,
        str | bytes | bytearray,
    ):
        return True
    return len(cast(Sequence[object], raw_interrupts)) == 0


def langchain_stream_action_count(interrupts: Sequence[object]) -> int:
    count = 0
    for interrupt in interrupts:
        value = getattr(interrupt, "value", interrupt)
        if not isinstance(value, Mapping):
            continue
        action_requests = cast(Mapping[object, object], value).get("action_requests")
        if isinstance(action_requests, Sequence) and not isinstance(
            action_requests,
            str | bytes | bytearray,
        ):
            count += len(cast(Sequence[object], action_requests))
    return count


def native_langgraph_stream_action_count(interrupts: Sequence[object]) -> int:
    count = 0
    for interrupt in interrupts:
        value = getattr(interrupt, "value", interrupt)
        if not isinstance(value, Mapping):
            continue
        approval_request = cast(Mapping[object, object], value).get("approval_request")
        if isinstance(approval_request, Mapping):
            count += 1
    return count


def langgraph_stream_chunk(raw_event: Mapping[str, object]) -> object | None:
    data = raw_event.get("data")
    if not isinstance(data, Mapping):
        return None
    typed_data = cast(Mapping[object, object], data)
    return typed_data.get("chunk")


def stream_chunk_text(chunk: object) -> str | None:
    if isinstance(chunk, Mapping):
        typed_chunk = cast(Mapping[object, object], chunk)
        text = typed_chunk.get("response_text")
        if isinstance(text, str):
            return text
        content = typed_chunk.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(stream_content_part_text(part) for part in cast(list[object], content))
        return None
    content = getattr(chunk, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(stream_content_part_text(part) for part in cast(list[object], content))
    return None


def stream_content_part_text(part: object) -> str:
    if isinstance(part, str):
        return part
    if isinstance(part, Mapping):
        typed_part = cast(Mapping[object, object], part)
        content_type = typed_part.get("type")
        if isinstance(content_type, str) and content_type != "text":
            return ""
        text = typed_part.get("text")
        return text if isinstance(text, str) else ""
    return ""


def langgraph_trace_id(raw_event: Mapping[str, object], fallback_trace_id: str) -> str:
    trace_id = raw_event.get("run_id")
    return trace_id if isinstance(trace_id, str) and trace_id.strip() else fallback_trace_id
