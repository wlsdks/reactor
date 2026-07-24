from __future__ import annotations

from langchain_core.messages import AIMessageChunk
from langgraph.types import Interrupt

from reactor.agents import streaming
from reactor.agents.events import AgentStreamEvent
from reactor.agents.streaming import (
    langchain_v2_stream_event_to_agent_event,
    langchain_v2_stream_interrupts,
    langgraph_stream_event_to_agent_event,
    replay_stream_events,
)
from reactor.persistence.run_store import RunEventRecord


def test_streaming_version_contract_distinguishes_raw_events_from_interrupt_projection() -> None:
    assert getattr(streaming, "LANGCHAIN_RAW_STREAM_EVENTS_VERSION", None) == "v2"
    assert getattr(streaming, "LANGGRAPH_INTERRUPT_STREAM_EVENTS_VERSION", None) == "v2"
    assert getattr(streaming, "LANGCHAIN_AGENT_STREAM_EVENTS_VERSION", None) == "v2"


def test_langchain_v2_projection_redacts_interrupt_arguments() -> None:
    interrupt = Interrupt(
        value={
            "action_requests": [
                {"name": "Webhook:send", "args": {"authorization": "private-credential"}}
            ]
        }
    )
    raw_event: dict[str, object] = {
        "event": "on_chain_stream",
        "run_id": "trace_1",
        "parent_ids": [],
        "metadata": {},
        "data": {"chunk": {"__interrupt__": (interrupt,)}},
    }

    event = langchain_v2_stream_event_to_agent_event(
        raw_event,
        run_id="run_1",
        sequence=7,
        fallback_trace_id="trace_1",
    )

    assert event is not None
    assert event.event_type == "run.stream.approval"
    assert event.payload == {"approval_status": "pending", "action_count": 1}
    assert "private-credential" not in repr(event.as_payload())
    assert langchain_v2_stream_interrupts(raw_event) == (interrupt,)


def test_native_langgraph_projection_redacts_interrupt_arguments() -> None:
    interrupt = Interrupt(
        value={
            "approval_status": "pending",
            "approval_request": {
                "tool_id": "Webhook:send",
                "input_payload": {"authorization": "private-credential"},
            },
        },
        id="interrupt_1",
    )
    raw_event: dict[str, object] = {
        "event": "on_chain_stream",
        "run_id": "trace_1",
        "parent_ids": [],
        "metadata": {},
        "data": {"chunk": {"__interrupt__": (interrupt,)}},
    }

    event = langgraph_stream_event_to_agent_event(
        raw_event,
        run_id="run_1",
        sequence=7,
        fallback_trace_id="trace_1",
    )

    assert event is not None
    assert event.event_type == "run.stream.approval"
    assert event.payload == {"approval_status": "pending", "action_count": 1}
    assert "private-credential" not in repr(event.as_payload())


def test_langchain_v2_projection_converts_message_frame_to_token() -> None:
    event = langchain_v2_stream_event_to_agent_event(
        {
            "event": "on_chat_model_stream",
            "run_id": "trace_model",
            "metadata": {"langgraph_node": "model"},
            "data": {"chunk": AIMessageChunk(content="hello")},
        },
        run_id="run_1",
        sequence=8,
        fallback_trace_id="trace_1",
    )

    assert event is not None
    assert event.event_type == "run.stream.token"
    assert event.graph_node == "model"
    assert event.payload == {"text": "hello"}


def test_stream_event_requires_replayable_payload_identity() -> None:
    event = AgentStreamEvent(
        run_id="run_1",
        sequence=4,
        event_type="run.stream.tool",
        graph_node="tool_executor",
        trace_id="trace_1",
        payload={"tool": "SearchServer:search_docs"},
    )

    assert event.as_payload() == {
        "run_id": "run_1",
        "sequence": 4,
        "graph_node": "tool_executor",
        "trace_id": "trace_1",
        "tool": "SearchServer:search_docs",
    }


def test_stream_replay_filters_by_sequence_and_stream_type() -> None:
    events = [
        RunEventRecord(sequence=1, event_type="run.created", payload={}),
        RunEventRecord(sequence=2, event_type="run.stream.started", payload={}),
        RunEventRecord(sequence=3, event_type="run.stream.token", payload={"text": "a"}),
        RunEventRecord(sequence=4, event_type="run.completed", payload={}),
    ]

    replayed = replay_stream_events(events, after_sequence=2)

    assert [event.sequence for event in replayed] == [3]


def test_langgraph_stream_projection_converts_state_update_to_token_event() -> None:
    event = langgraph_stream_event_to_agent_event(
        {
            "event": "on_chain_stream",
            "run_id": "trace_model",
            "metadata": {"langgraph_node": "model"},
            "data": {"chunk": {"response_text": "hello"}},
        },
        run_id="run_1",
        sequence=7,
        fallback_trace_id="trace_fallback",
    )

    assert event is not None
    assert event.event_type == "run.stream.token"
    assert event.graph_node == "model"
    assert event.trace_id == "trace_model"
    assert event.payload == {"text": "hello"}


def test_langgraph_stream_projection_converts_serialized_chat_model_chunk() -> None:
    event = langgraph_stream_event_to_agent_event(
        {
            "event": "on_chat_model_stream",
            "run_id": "trace_chat",
            "metadata": {"langgraph_node": "model"},
            "data": {
                "chunk": {
                    "content": [
                        {"type": "text", "text": "serialized "},
                        {"type": "text", "text": "chunk"},
                    ]
                }
            },
        },
        run_id="run_1",
        sequence=10,
        fallback_trace_id="trace_fallback",
    )

    assert event is not None
    assert event.event_type == "run.stream.token"
    assert event.graph_node == "model"
    assert event.trace_id == "trace_chat"
    assert event.payload == {"text": "serialized chunk"}


def test_langgraph_stream_projection_omits_non_text_content_blocks() -> None:
    event = langgraph_stream_event_to_agent_event(
        {
            "event": "on_chat_model_stream",
            "run_id": "trace_chat",
            "metadata": {"langgraph_node": "model"},
            "data": {
                "chunk": {
                    "content": [
                        {"type": "reasoning", "text": "internal reasoning"},
                        {"type": "text", "text": "visible answer"},
                    ]
                }
            },
        },
        run_id="run_1",
        sequence=11,
        fallback_trace_id="trace_fallback",
    )

    assert event is not None
    assert event.event_type == "run.stream.token"
    assert event.payload == {"text": "visible answer"}


def test_langgraph_stream_projection_converts_tool_results_to_tool_event() -> None:
    event = langgraph_stream_event_to_agent_event(
        {
            "event": "on_chain_stream",
            "metadata": {"langgraph_node": "tool_executor"},
            "data": {
                "chunk": {
                    "tool_results": [{"tool_id": "SearchServer:search_docs", "status": "success"}]
                }
            },
        },
        run_id="run_1",
        sequence=8,
        fallback_trace_id="trace_fallback",
    )

    assert event is not None
    assert event.event_type == "run.stream.tool"
    assert event.graph_node == "tool_executor"
    assert event.trace_id == "trace_fallback"
    assert event.payload == {
        "tool_results": [{"tool_id": "SearchServer:search_docs", "status": "success"}]
    }


def test_langgraph_stream_projection_ignores_pending_approval_without_interrupt() -> None:
    event = langgraph_stream_event_to_agent_event(
        {
            "event": "on_chain_stream",
            "run_id": "trace_approval",
            "metadata": {"langgraph_node": "approval_gate"},
            "data": {"chunk": {"approval_status": "pending"}},
        },
        run_id="run_1",
        sequence=9,
        fallback_trace_id="trace_fallback",
    )

    assert event is None
