from __future__ import annotations

from operator import add
from typing import Annotated, TypedDict, cast

import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from reactor.agents.checkpoint_fork import (
    CheckpointForkError,
    checkpoint_id_from_config,
    materialize_checkpoint_fork,
)
from reactor.agents.runtime_config import langgraph_durable_config


class ForkState(TypedDict):
    values: Annotated[list[str], add]


class TamperedReadSaver(InMemorySaver):
    def __init__(self, *, key: str, value: str) -> None:
        super().__init__()
        self.tamper_key = key
        self.tamper_value = value
        self.tamper_reads = False

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        checkpoint_tuple = await super().aget_tuple(config)
        if checkpoint_tuple is None or not self.tamper_reads:
            return checkpoint_tuple
        configurable = dict(checkpoint_tuple.config.get("configurable", {}))
        configurable[self.tamper_key] = self.tamper_value
        return checkpoint_tuple._replace(
            config={**checkpoint_tuple.config, "configurable": configurable}
        )


class TamperedCheckpointPayloadSaver(InMemorySaver):
    tamper_reads = False

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        checkpoint_tuple = await super().aget_tuple(config)
        if checkpoint_tuple is None or not self.tamper_reads:
            return checkpoint_tuple
        checkpoint = dict(checkpoint_tuple.checkpoint)
        checkpoint["id"] = "unexpected-payload-checkpoint-id"
        return checkpoint_tuple._replace(checkpoint=cast(Checkpoint, checkpoint))


def build_fork_graph(checkpointer: InMemorySaver):
    def record(state: ForkState) -> dict[str, list[str]]:
        del state
        return {"values": ["recorded"]}

    builder = StateGraph(ForkState)
    builder.add_node("record", record)
    builder.add_edge(START, "record")
    builder.add_edge("record", END)
    return builder.compile(checkpointer=checkpointer)


async def test_materialize_checkpoint_fork_copies_state_to_empty_target_scope() -> None:
    checkpointer = InMemorySaver()
    graph = build_fork_graph(checkpointer)
    source_config = langgraph_durable_config(
        tenant_id="tenant_1",
        thread_id="thread_source",
        checkpoint_ns="reactor",
    )
    await graph.ainvoke({"values": ["source"]}, config=source_config)
    source_tuple = await checkpointer.aget_tuple(source_config)
    assert source_tuple is not None
    source_checkpoint_id = checkpoint_id_from_config(source_tuple.config)
    assert source_checkpoint_id is not None

    result = await materialize_checkpoint_fork(
        checkpointer,
        tenant_id="tenant_1",
        source_thread_id="thread_source",
        source_checkpoint_ns="reactor",
        source_checkpoint_id=source_checkpoint_id,
        target_thread_id="thread_target",
        target_checkpoint_ns="fork",
    )
    target_config = langgraph_durable_config(
        tenant_id="tenant_1",
        thread_id="thread_target",
        checkpoint_ns="fork",
    )

    assert result.mode == "copied_to_target_scope"
    assert (await graph.aget_state(target_config)).values == {"values": ["source", "recorded"]}
    continued = await graph.ainvoke({"values": ["target"]}, config=target_config)
    assert continued == {"values": ["source", "recorded", "target", "recorded"]}


async def test_materialize_checkpoint_fork_fails_closed_for_nonempty_target() -> None:
    checkpointer = InMemorySaver()
    graph = build_fork_graph(checkpointer)
    source_config = langgraph_durable_config(
        tenant_id="tenant_1",
        thread_id="thread_source",
        checkpoint_ns="reactor",
    )
    target_config = langgraph_durable_config(
        tenant_id="tenant_1",
        thread_id="thread_target",
        checkpoint_ns="fork",
    )
    await graph.ainvoke({"values": ["source"]}, config=source_config)
    await graph.ainvoke({"values": ["target"]}, config=target_config)
    source_tuple = await checkpointer.aget_tuple(source_config)
    assert source_tuple is not None

    with pytest.raises(CheckpointForkError, match="target_checkpoint_scope_not_empty"):
        await materialize_checkpoint_fork(
            checkpointer,
            tenant_id="tenant_1",
            source_thread_id="thread_source",
            source_checkpoint_ns="reactor",
            source_checkpoint_id=required_checkpoint_id(source_tuple.config),
            target_thread_id="thread_target",
            target_checkpoint_ns="fork",
        )


async def test_materialize_checkpoint_fork_cannot_cross_tenants() -> None:
    checkpointer = InMemorySaver()
    graph = build_fork_graph(checkpointer)
    source_config = langgraph_durable_config(
        tenant_id="tenant_1",
        thread_id="thread_source",
        checkpoint_ns="reactor",
    )
    await graph.ainvoke({"values": ["source"]}, config=source_config)
    source_tuple = await checkpointer.aget_tuple(source_config)
    assert source_tuple is not None

    with pytest.raises(CheckpointForkError, match="source_checkpoint_not_found"):
        await materialize_checkpoint_fork(
            checkpointer,
            tenant_id="tenant_2",
            source_thread_id="thread_source",
            source_checkpoint_ns="reactor",
            source_checkpoint_id=required_checkpoint_id(source_tuple.config),
            target_thread_id="thread_target",
            target_checkpoint_ns="fork",
        )


async def test_materialize_checkpoint_fork_rejects_written_scope_mismatch() -> None:
    class WrongScopeSaver(InMemorySaver):
        async def aput(
            self,
            config: RunnableConfig,
            checkpoint: Checkpoint,
            metadata: CheckpointMetadata,
            new_versions: ChannelVersions,
        ) -> RunnableConfig:
            written = await super().aput(config, checkpoint, metadata, new_versions)
            configurable = dict(written.get("configurable", {}))
            configurable["thread_id"] = "unexpected-checkpoint-scope"
            return {**written, "configurable": configurable}

    checkpointer = WrongScopeSaver()
    graph = build_fork_graph(checkpointer)
    source_config = langgraph_durable_config(
        tenant_id="tenant_1",
        thread_id="thread_source",
        checkpoint_ns="reactor",
    )
    await graph.ainvoke({"values": ["source"]}, config=source_config)
    source_tuple = await checkpointer.aget_tuple(source_config)
    assert source_tuple is not None

    with pytest.raises(CheckpointForkError, match="target_checkpoint_write_scope_mismatch"):
        await materialize_checkpoint_fork(
            checkpointer,
            tenant_id="tenant_1",
            source_thread_id="thread_source",
            source_checkpoint_ns="reactor",
            source_checkpoint_id=required_checkpoint_id(source_tuple.config),
            target_thread_id="thread_target",
            target_checkpoint_ns="fork",
        )


async def test_materialize_checkpoint_fork_rejects_source_scope_mismatch() -> None:
    checkpointer = TamperedReadSaver(
        key="thread_id",
        value="unexpected-source-scope",
    )
    graph = build_fork_graph(checkpointer)
    source_config = langgraph_durable_config(
        tenant_id="tenant_1",
        thread_id="thread_source",
        checkpoint_ns="reactor",
    )
    await graph.ainvoke({"values": ["source"]}, config=source_config)
    source_tuple = await checkpointer.aget_tuple(source_config)
    assert source_tuple is not None
    checkpointer.tamper_reads = True

    with pytest.raises(CheckpointForkError, match="source_checkpoint_scope_mismatch"):
        await materialize_checkpoint_fork(
            checkpointer,
            tenant_id="tenant_1",
            source_thread_id="thread_source",
            source_checkpoint_ns="reactor",
            source_checkpoint_id=required_checkpoint_id(source_tuple.config),
            target_thread_id="thread_target",
            target_checkpoint_ns="fork",
        )


async def test_materialize_checkpoint_fork_rejects_source_checkpoint_id_mismatch() -> None:
    checkpointer = TamperedReadSaver(
        key="checkpoint_id",
        value="unexpected-checkpoint-id",
    )
    graph = build_fork_graph(checkpointer)
    source_config = langgraph_durable_config(
        tenant_id="tenant_1",
        thread_id="thread_source",
        checkpoint_ns="reactor",
    )
    await graph.ainvoke({"values": ["source"]}, config=source_config)
    source_tuple = await checkpointer.aget_tuple(source_config)
    assert source_tuple is not None
    checkpointer.tamper_reads = True

    with pytest.raises(CheckpointForkError, match="source_checkpoint_id_mismatch"):
        await materialize_checkpoint_fork(
            checkpointer,
            tenant_id="tenant_1",
            source_thread_id="thread_source",
            source_checkpoint_ns="reactor",
            source_checkpoint_id=required_checkpoint_id(source_tuple.config),
            target_thread_id="thread_target",
            target_checkpoint_ns="fork",
        )


async def test_materialize_checkpoint_fork_rejects_source_payload_id_mismatch() -> None:
    checkpointer = TamperedCheckpointPayloadSaver()
    graph = build_fork_graph(checkpointer)
    source_config = langgraph_durable_config(
        tenant_id="tenant_1",
        thread_id="thread_source",
        checkpoint_ns="reactor",
    )
    await graph.ainvoke({"values": ["source"]}, config=source_config)
    source_tuple = await checkpointer.aget_tuple(source_config)
    assert source_tuple is not None
    checkpointer.tamper_reads = True

    with pytest.raises(CheckpointForkError, match="source_checkpoint_payload_id_mismatch"):
        await materialize_checkpoint_fork(
            checkpointer,
            tenant_id="tenant_1",
            source_thread_id="thread_source",
            source_checkpoint_ns="reactor",
            source_checkpoint_id=required_checkpoint_id(source_tuple.config),
            target_thread_id="thread_target",
            target_checkpoint_ns="fork",
        )


def required_checkpoint_id(config: RunnableConfig) -> str:
    checkpoint_id = checkpoint_id_from_config(config)
    assert checkpoint_id is not None
    return checkpoint_id
