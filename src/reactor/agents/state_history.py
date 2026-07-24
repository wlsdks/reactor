from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, cast

from langchain_core.runnables import RunnableConfig

from reactor.agents.runtime_config import (
    LANGGRAPH_ROOT_CHECKPOINT_NS,
    langgraph_checkpoint_thread_id,
)


class CheckpointHistoryReader(Protocol):
    def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[object]: ...


@dataclass(frozen=True)
class GraphStateHistoryEntry:
    checkpoint_id: str
    parent_checkpoint_id: str | None
    created_at: str | None
    source: str | None
    step: int | None
    state_keys: list[str]
    updated_channels: list[str]
    pending_write_count: int

    def as_response(self) -> dict[str, object]:
        return {
            "checkpointId": self.checkpoint_id,
            "parentCheckpointId": self.parent_checkpoint_id,
            "createdAt": self.created_at,
            "source": self.source,
            "step": self.step,
            "stateKeys": self.state_keys,
            "updatedChannels": self.updated_channels,
            "pendingWriteCount": self.pending_write_count,
        }


@dataclass(frozen=True)
class GraphStateHistory:
    run_id: str
    thread_id: str
    checkpoint_ns: str
    resolved_checkpoint_ns: str
    namespace_fallback_used: bool
    entries: list[GraphStateHistoryEntry]

    def as_response(self) -> dict[str, object]:
        return {
            "runId": self.run_id,
            "threadId": self.thread_id,
            "checkpointNs": self.checkpoint_ns,
            "resolvedCheckpointNs": self.resolved_checkpoint_ns,
            "namespaceFallbackUsed": self.namespace_fallback_used,
            "entries": [entry.as_response() for entry in self.entries],
        }


async def read_graph_state_history(
    checkpointer: CheckpointHistoryReader,
    *,
    run_id: str,
    tenant_id: str,
    thread_id: str,
    checkpoint_ns: str,
    limit: int,
) -> GraphStateHistory:
    clean_limit = max(1, min(limit, 100))
    checkpoint_thread_id = langgraph_checkpoint_thread_id(
        tenant_id=tenant_id,
        thread_id=thread_id,
        checkpoint_ns=checkpoint_ns,
    )
    config: RunnableConfig = {
        "configurable": {
            "thread_id": checkpoint_thread_id,
            "checkpoint_ns": LANGGRAPH_ROOT_CHECKPOINT_NS,
        }
    }
    entries = await collect_graph_state_history_entries(
        checkpointer,
        config=config,
        limit=clean_limit,
    )
    resolved_checkpoint_ns = LANGGRAPH_ROOT_CHECKPOINT_NS
    namespace_fallback_used = False
    return GraphStateHistory(
        run_id=run_id,
        thread_id=thread_id,
        checkpoint_ns=checkpoint_ns,
        resolved_checkpoint_ns=resolved_checkpoint_ns,
        namespace_fallback_used=namespace_fallback_used,
        entries=entries,
    )


async def collect_graph_state_history_entries(
    checkpointer: CheckpointHistoryReader,
    *,
    config: RunnableConfig,
    limit: int,
) -> list[GraphStateHistoryEntry]:
    entries: list[GraphStateHistoryEntry] = []
    async for checkpoint in checkpointer.alist(config, limit=limit):
        entries.append(graph_state_history_entry(checkpoint))
    return entries


def graph_state_history_entry(checkpoint_tuple: object) -> GraphStateHistoryEntry:
    checkpoint = mapping_attr(checkpoint_tuple, "checkpoint")
    metadata = mapping_attr(checkpoint_tuple, "metadata")
    config = mapping_attr(checkpoint_tuple, "config")
    parent_config = mapping_attr(checkpoint_tuple, "parent_config")
    channel_values = mapping_value(checkpoint, "channel_values")
    checkpoint_id = config_checkpoint_id(config) or string_value(checkpoint.get("id")) or ""
    return GraphStateHistoryEntry(
        checkpoint_id=checkpoint_id,
        parent_checkpoint_id=config_checkpoint_id(parent_config),
        created_at=string_value(checkpoint.get("ts")),
        source=string_value(metadata.get("source")),
        step=int_value(metadata.get("step")),
        state_keys=sorted(str(key) for key in channel_values.keys()),
        updated_channels=string_list(checkpoint.get("updated_channels")),
        pending_write_count=len(list_attr(checkpoint_tuple, "pending_writes")),
    )


def mapping_attr(value: object, name: str) -> Mapping[str, Any]:
    raw = getattr(value, name, {})
    return cast(Mapping[str, Any], raw if isinstance(raw, Mapping) else {})


def list_attr(value: object, name: str) -> list[object]:
    raw = getattr(value, name, [])
    return list(cast(list[object], raw)) if isinstance(raw, list) else []


def mapping_value(value: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    raw = value.get(name)
    return cast(Mapping[str, Any], raw if isinstance(raw, Mapping) else {})


def config_checkpoint_id(config: Mapping[str, Any]) -> str | None:
    configurable = mapping_value(config, "configurable")
    return string_value(configurable.get("checkpoint_id"))


def string_value(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


def int_value(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in cast(list[object], value)]
