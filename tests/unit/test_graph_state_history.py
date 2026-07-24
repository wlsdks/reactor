from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, cast

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver

from reactor.agents.graph import GRAPH_STAGE_ORDER, build_reactor_graph
from reactor.agents.runtime_config import (
    langgraph_checkpoint_thread_id,
    langgraph_durable_config,
)
from reactor.agents.state import ReactorState
from reactor.agents.state_history import read_graph_state_history


async def test_graph_state_history_reads_checkpoint_summaries_without_raw_state() -> None:
    checkpointer = InMemorySaver()
    graph = build_reactor_graph(checkpointer=checkpointer)

    await graph.ainvoke(
        ReactorState(
            run_id="run_1",
            tenant_id="tenant_1",
            user_id="user_1",
            messages=[HumanMessage(content="hello")],
            max_tool_calls=1,
            tool_call_count=0,
        ),
        config=langgraph_durable_config(
            tenant_id="tenant_1",
            thread_id="thread_1",
            checkpoint_ns="reactor",
        ),
    )

    history = await read_graph_state_history(
        checkpointer,
        run_id="run_1",
        tenant_id="tenant_1",
        thread_id="thread_1",
        checkpoint_ns="reactor",
        limit=3,
    )

    response = history.as_response()
    assert response["runId"] == "run_1"
    assert response["threadId"] == "thread_1"
    assert response["checkpointNs"] == "reactor"
    entries = cast(list[dict[str, Any]], response["entries"])
    assert len(entries) == 3
    assert entries[0]["checkpointId"]
    assert entries[0]["step"] == len(GRAPH_STAGE_ORDER)
    assert "response_metadata" in entries[0]["stateKeys"]
    assert "response_text" in entries[0]["stateKeys"]
    assert "responseText" not in entries[0]
    assert "messages" not in entries[0]


async def test_graph_state_history_clamps_limit() -> None:
    checkpointer = InMemorySaver()
    graph = build_reactor_graph(checkpointer=checkpointer)

    await graph.ainvoke(
        ReactorState(
            run_id="run_1",
            tenant_id="tenant_1",
            user_id="user_1",
            messages=[HumanMessage(content="hello")],
            max_tool_calls=1,
            tool_call_count=0,
        ),
        config=langgraph_durable_config(
            tenant_id="tenant_1",
            thread_id="thread_1",
            checkpoint_ns="reactor",
        ),
    )

    history = await read_graph_state_history(
        checkpointer,
        run_id="run_1",
        tenant_id="tenant_1",
        thread_id="thread_1",
        checkpoint_ns="reactor",
        limit=1000,
    )

    assert len(history.entries) < 100


async def test_graph_state_history_reads_from_requested_checkpoint_namespace() -> None:
    checkpointer = RecordingHistoryReader()

    await read_graph_state_history(
        checkpointer,
        run_id="run_1",
        tenant_id="tenant_1",
        thread_id="thread_1",
        checkpoint_ns="tenant-research",
        limit=5,
    )

    assert checkpointer.seen_configs[0] == {
        "configurable": {
            "thread_id": langgraph_checkpoint_thread_id(
                tenant_id="tenant_1",
                thread_id="thread_1",
                checkpoint_ns="tenant-research",
            ),
            "checkpoint_ns": "",
        }
    }


async def test_graph_state_history_does_not_fall_back_to_unscoped_legacy_thread() -> None:
    checkpointer = RecordingHistoryReader()

    history = await read_graph_state_history(
        checkpointer,
        run_id="run_1",
        tenant_id="tenant_1",
        thread_id="thread_1",
        checkpoint_ns="tenant-research",
        limit=5,
    )

    response = history.as_response()
    assert response["checkpointNs"] == "tenant-research"
    assert response["resolvedCheckpointNs"] == ""
    assert response["namespaceFallbackUsed"] is False
    assert response["entries"] == []
    assert checkpointer.seen_configs == [
        {
            "configurable": {
                "thread_id": langgraph_checkpoint_thread_id(
                    tenant_id="tenant_1",
                    thread_id="thread_1",
                    checkpoint_ns="tenant-research",
                ),
                "checkpoint_ns": "",
            }
        }
    ]


class RecordingHistoryReader:
    def __init__(self) -> None:
        self.seen_configs: list[RunnableConfig | None] = []

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[object]:
        del filter, before, limit
        self.seen_configs.append(config)
        if False:
            yield object()
