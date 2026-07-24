from __future__ import annotations

from typing import TypedDict

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from reactor.agents.runtime_config import (
    initial_reactor_state,
    langgraph_checkpoint_thread_id,
    langgraph_durable_config,
)
from reactor.agents.state import REACTOR_STATE_SCHEMA_VERSION


class ReplayState(TypedDict):
    value: str


def test_initial_reactor_state_is_versioned_for_first_checkpoint() -> None:
    state = initial_reactor_state(
        run_id="run_1",
        tenant_id="tenant_1",
        user_id="user_1",
        trusted_user_groups=("engineering",),
        messages=[HumanMessage(content="hello")],
        max_tool_calls=3,
        checkpoint_ns="reactor",
    )

    assert state.get("state_schema_version") == REACTOR_STATE_SCHEMA_VERSION
    assert state.get("run_id") == "run_1"
    assert state.get("trusted_user_groups") == ("engineering",)
    assert state.get("tool_call_count") == 0
    assert state.get("max_tool_calls") == 3
    assert state.get("profile_checkpoint_ns") == "reactor"


def test_initial_reactor_state_requires_durable_checkpoint_namespace() -> None:
    with pytest.raises(ValueError, match="checkpoint_ns is required"):
        initial_reactor_state(
            run_id="run_1",
            tenant_id="tenant_1",
            user_id="user_1",
            trusted_user_groups=(),
            messages=[HumanMessage(content="hello")],
            max_tool_calls=3,
            checkpoint_ns="   ",
        )


def test_langgraph_durable_config_only_contains_checkpoint_identity() -> None:
    checkpoint_thread_id = langgraph_checkpoint_thread_id(
        tenant_id="tenant_1",
        thread_id="thread_1",
        checkpoint_ns="reactor",
    )
    assert langgraph_durable_config(
        tenant_id="tenant_1",
        thread_id="thread_1",
        checkpoint_ns="reactor",
    ) == {
        "recursion_limit": 25,
        "configurable": {
            "thread_id": checkpoint_thread_id,
            "checkpoint_ns": "",
        },
    }


def test_langgraph_durable_config_can_pin_checkpoint_id_for_replay() -> None:
    assert langgraph_durable_config(
        tenant_id="tenant_1",
        thread_id="thread_1",
        checkpoint_ns="reactor",
        checkpoint_id="checkpoint_7",
    ) == {
        "recursion_limit": 25,
        "configurable": {
            "thread_id": langgraph_checkpoint_thread_id(
                tenant_id="tenant_1",
                thread_id="thread_1",
                checkpoint_ns="reactor",
            ),
            "checkpoint_ns": "",
            "checkpoint_id": "checkpoint_7",
        },
    }


def test_langgraph_durable_config_accepts_explicit_recursion_limit() -> None:
    assert langgraph_durable_config(
        tenant_id="tenant_1",
        thread_id="thread_1",
        checkpoint_ns="reactor",
        recursion_limit=7,
    ) == {
        "recursion_limit": 7,
        "configurable": {
            "thread_id": langgraph_checkpoint_thread_id(
                tenant_id="tenant_1",
                thread_id="thread_1",
                checkpoint_ns="reactor",
            ),
            "checkpoint_ns": "",
        },
    }


def test_langgraph_durable_config_accepts_native_trace_fields() -> None:
    assert langgraph_durable_config(
        tenant_id="tenant_1",
        thread_id="thread_1",
        checkpoint_ns="reactor",
        run_name="reactor.langchain_agent.invoke",
        tags=["reactor", "runtime:langchain_agent"],
        metadata={"reactor.runtime": "langchain_agent"},
    ) == {
        "recursion_limit": 25,
        "run_name": "reactor.langchain_agent.invoke",
        "tags": ["reactor", "runtime:langchain_agent"],
        "metadata": {"reactor.runtime": "langchain_agent"},
        "configurable": {
            "thread_id": langgraph_checkpoint_thread_id(
                tenant_id="tenant_1",
                thread_id="thread_1",
                checkpoint_ns="reactor",
            ),
            "checkpoint_ns": "",
        },
    }


@pytest.mark.parametrize("recursion_limit", [0, -1, True])
def test_langgraph_durable_config_rejects_invalid_recursion_limit(
    recursion_limit: int,
) -> None:
    with pytest.raises(ValueError, match="recursion_limit must be greater than 0"):
        langgraph_durable_config(
            tenant_id="tenant_1",
            thread_id="thread_1",
            checkpoint_ns="reactor",
            recursion_limit=recursion_limit,
        )


@pytest.mark.parametrize(
    ("thread_id", "checkpoint_ns", "checkpoint_id"),
    [
        ("", "reactor", None),
        ("  ", "reactor", None),
        ("thread_1", "", None),
        ("thread_1", "  ", None),
        ("thread_1", "reactor", ""),
        ("thread_1", "reactor", "  "),
    ],
)
def test_langgraph_durable_config_rejects_blank_checkpoint_identity(
    thread_id: str,
    checkpoint_ns: str,
    checkpoint_id: str | None,
) -> None:
    with pytest.raises(ValueError, match="must not be blank"):
        langgraph_durable_config(
            tenant_id="tenant_1",
            thread_id=thread_id,
            checkpoint_ns=checkpoint_ns,
            checkpoint_id=checkpoint_id,
        )


def test_langgraph_checkpoint_thread_id_is_tenant_and_namespace_scoped() -> None:
    base = langgraph_checkpoint_thread_id(
        tenant_id="tenant_1",
        thread_id="thread_1",
        checkpoint_ns="reactor",
    )

    assert base.startswith("reactor:checkpoint:v1:")
    assert "tenant_1" not in base
    assert "thread_1" not in base
    assert base != langgraph_checkpoint_thread_id(
        tenant_id="tenant_2",
        thread_id="thread_1",
        checkpoint_ns="reactor",
    )
    assert base != langgraph_checkpoint_thread_id(
        tenant_id="tenant_1",
        thread_id="thread_1",
        checkpoint_ns="fork",
    )


async def test_langgraph_root_config_preserves_checkpoint_pin_for_real_replay() -> None:
    def copy_value(state: ReplayState) -> ReplayState:
        return {"value": state["value"]}

    builder = StateGraph(ReplayState)
    builder.add_node("copy", copy_value)
    builder.add_edge(START, "copy")
    builder.add_edge("copy", END)
    checkpointer = InMemorySaver()
    graph = builder.compile(checkpointer=checkpointer)
    base_config = langgraph_durable_config(
        tenant_id="tenant_1",
        thread_id="thread_1",
        checkpoint_ns="reactor",
    )
    await graph.ainvoke({"value": "first"}, config=base_config)
    checkpoints = [item async for item in checkpointer.alist(base_config)]
    first_input_checkpoint_id = checkpoints[-1].config.get("configurable", {}).get("checkpoint_id")
    assert isinstance(first_input_checkpoint_id, str)
    await graph.ainvoke({"value": "latest"}, config=base_config)

    replay_config = langgraph_durable_config(
        tenant_id="tenant_1",
        thread_id="thread_1",
        checkpoint_ns="reactor",
        checkpoint_id=first_input_checkpoint_id,
    )
    replayed = await graph.ainvoke(None, config=replay_config)

    replay_configurable = replay_config.get("configurable", {})
    assert replay_configurable.get("checkpoint_ns") == ""
    assert replay_configurable.get("checkpoint_id") == first_input_checkpoint_id
    assert replayed["value"] == "first"
