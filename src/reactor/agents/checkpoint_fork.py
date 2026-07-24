from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, cast

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver

from reactor.agents.runtime_config import langgraph_durable_config


class CheckpointForkError(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class CheckpointForkResult:
    checkpoint_id: str
    mode: str


async def latest_checkpoint_id(
    checkpointer: object | None,
    *,
    config: RunnableConfig,
) -> str | None:
    if not isinstance(checkpointer, BaseCheckpointSaver):
        return None
    try:
        checkpoint_tuple = await cast(BaseCheckpointSaver[Any], checkpointer).aget_tuple(config)
    except Exception:
        return None
    if checkpoint_tuple is None:
        return None
    return checkpoint_id_from_config(checkpoint_tuple.config)


async def materialize_checkpoint_fork(
    checkpointer: object | None,
    *,
    tenant_id: str,
    source_thread_id: str,
    source_checkpoint_ns: str,
    source_checkpoint_id: str,
    target_thread_id: str,
    target_checkpoint_ns: str,
) -> CheckpointForkResult:
    if not isinstance(checkpointer, BaseCheckpointSaver):
        raise CheckpointForkError("checkpointer_unavailable")
    typed_checkpointer = cast(BaseCheckpointSaver[Any], checkpointer)

    try:
        return await _materialize_checkpoint_fork(
            typed_checkpointer,
            tenant_id=tenant_id,
            source_thread_id=source_thread_id,
            source_checkpoint_ns=source_checkpoint_ns,
            source_checkpoint_id=source_checkpoint_id,
            target_thread_id=target_thread_id,
            target_checkpoint_ns=target_checkpoint_ns,
        )
    except CheckpointForkError:
        raise
    except Exception as error:
        raise CheckpointForkError("checkpoint_store_error") from error


async def _materialize_checkpoint_fork(
    checkpointer: BaseCheckpointSaver[Any],
    *,
    tenant_id: str,
    source_thread_id: str,
    source_checkpoint_ns: str,
    source_checkpoint_id: str,
    target_thread_id: str,
    target_checkpoint_ns: str,
) -> CheckpointForkResult:

    source_config = langgraph_durable_config(
        tenant_id=tenant_id,
        thread_id=source_thread_id,
        checkpoint_ns=source_checkpoint_ns,
        checkpoint_id=source_checkpoint_id,
    )
    source_tuple = await checkpointer.aget_tuple(source_config)
    if source_tuple is None:
        raise CheckpointForkError("source_checkpoint_not_found")
    if checkpoint_scope(source_tuple.config) != checkpoint_scope(source_config):
        raise CheckpointForkError("source_checkpoint_scope_mismatch")
    if checkpoint_id_from_config(source_tuple.config) != source_checkpoint_id:
        raise CheckpointForkError("source_checkpoint_id_mismatch")

    source_checkpoint = source_tuple.checkpoint
    if source_checkpoint.get("id") != source_checkpoint_id:
        raise CheckpointForkError("source_checkpoint_payload_id_mismatch")
    require_channel_versions(source_checkpoint.get("channel_versions"))
    pending_writes = getattr(source_tuple, "pending_writes", ())
    if pending_writes:
        raise CheckpointForkError("source_checkpoint_has_pending_writes")

    target_config = langgraph_durable_config(
        tenant_id=tenant_id,
        thread_id=target_thread_id,
        checkpoint_ns=target_checkpoint_ns,
    )
    if checkpoint_scope(source_config) == checkpoint_scope(target_config):
        return CheckpointForkResult(
            checkpoint_id=source_checkpoint_id,
            mode="pinned_source_scope",
        )
    if await checkpointer.aget_tuple(target_config) is not None:
        raise CheckpointForkError("target_checkpoint_scope_not_empty")

    written_config = await checkpointer.aput(
        target_config,
        deepcopy(source_tuple.checkpoint),
        deepcopy(source_tuple.metadata),
        deepcopy(source_tuple.checkpoint["channel_versions"]),
    )
    if checkpoint_scope(written_config) != checkpoint_scope(target_config):
        raise CheckpointForkError("target_checkpoint_write_scope_mismatch")
    written_checkpoint_id = checkpoint_id_from_config(written_config)
    if written_checkpoint_id is None:
        raise CheckpointForkError("target_checkpoint_write_failed")
    return CheckpointForkResult(
        checkpoint_id=written_checkpoint_id,
        mode="copied_to_target_scope",
    )


def checkpoint_scope(config: RunnableConfig) -> tuple[str, str]:
    configurable = config.get("configurable", {})
    return (
        str(configurable.get("thread_id", "")),
        str(configurable.get("checkpoint_ns", "")),
    )


def require_channel_versions(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CheckpointForkError("invalid_source_checkpoint")
    return cast(Mapping[str, Any], value)


def checkpoint_id_from_config(config: RunnableConfig) -> str | None:
    value = config.get("configurable", {}).get("checkpoint_id")
    return value if isinstance(value, str) and value else None
