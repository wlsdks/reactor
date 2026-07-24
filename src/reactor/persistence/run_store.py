from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol

from sqlalchemy import Select, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reactor.kernel.ids import new_id
from reactor.persistence.models import (
    AgentRun,
    AgentRunEvent,
    PendingApproval,
    RunQueue,
    ToolInvocation,
)
from reactor.tools.approval import CANCELLED_APPROVAL_STATUS, PENDING_APPROVAL_STATUS

RunResumeRuntime = Literal["langgraph", "langchain_agent"]


@dataclass(frozen=True)
class RunEventRecord:
    sequence: int
    event_type: str
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class RunCompletionEvent:
    event_type: str
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class SessionRunRecord:
    run_id: str
    tenant_id: str
    user_id: str
    thread_id: str
    checkpoint_ns: str
    status: str
    input_text: str
    response_text: str | None
    created_at: str
    updated_at: str
    metadata: Mapping[str, Any]


@dataclass(frozen=True)
class SessionListRecord:
    items: list[SessionRunRecord]
    total: int


@dataclass(frozen=True)
class AgentRunMigrationRecord:
    id: str
    tenant_id: str
    user_id: str
    thread_id: str
    checkpoint_ns: str
    status: str
    input_text: str
    response_text: str | None
    error_code: str | None
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    def validate(self) -> None:
        require_non_blank(
            ("id", self.id),
            ("tenant_id", self.tenant_id),
            ("user_id", self.user_id),
            ("thread_id", self.thread_id),
            ("checkpoint_ns", self.checkpoint_ns),
            ("status", self.status),
        )


@dataclass(frozen=True)
class AgentRunEventMigrationRecord:
    id: int | None
    run_id: str
    tenant_id: str
    sequence: int
    event_type: str
    payload: dict[str, Any]
    created_at: datetime

    def validate(self) -> None:
        require_non_blank(
            ("run_id", self.run_id),
            ("tenant_id", self.tenant_id),
            ("event_type", self.event_type),
        )


class RunRecord(Protocol):
    @property
    def run_id(self) -> str: ...

    @property
    def tenant_id(self) -> str: ...

    @property
    def user_id(self) -> str: ...

    @property
    def thread_id(self) -> str: ...

    @property
    def checkpoint_ns(self) -> str: ...

    @property
    def status(self) -> str: ...

    @property
    def response(self) -> str: ...


class RunStore(Protocol):
    async def claim_interrupted_resume(
        self,
        *,
        run_id: str,
        tenant_id: str,
        approval_id: str,
        claimed_by: str,
        runtime: RunResumeRuntime,
    ) -> bool: ...

    async def record_started(
        self,
        *,
        run_id: str,
        tenant_id: str,
        user_id: str,
        thread_id: str,
        checkpoint_ns: str,
        input_text: str,
        metadata: Mapping[str, Any],
    ) -> str: ...

    async def record_completed(
        self,
        *,
        result: RunRecord,
        metadata: Mapping[str, Any],
        completion_events: Sequence[RunCompletionEvent] = (),
    ) -> bool | None: ...

    async def record_cancelled_if_running(
        self,
        *,
        result: RunRecord,
        metadata: Mapping[str, Any],
    ) -> bool: ...

    async def record_cancelled_if_active(
        self,
        *,
        result: RunRecord,
        metadata: Mapping[str, Any],
    ) -> bool: ...

    async def record_event(
        self,
        *,
        run_id: str,
        tenant_id: str,
        sequence: int,
        event_type: str,
        payload: Mapping[str, Any],
    ) -> None: ...

    async def list_events(
        self,
        *,
        run_id: str,
        tenant_id: str | None = None,
        after_sequence: int = 0,
    ) -> list[RunEventRecord]: ...

    async def has_slack_thread_run(
        self,
        *,
        tenant_id: str,
        thread_id: str,
    ) -> bool: ...


class SessionStore(Protocol):
    async def list_sessions(
        self,
        *,
        tenant_id: str,
        user_id: str | None,
        limit: int,
        offset: int,
    ) -> SessionListRecord: ...

    async def find_session(self, *, run_id: str) -> SessionRunRecord | None: ...

    async def list_recent_runs(
        self,
        *,
        tenant_id: str,
        limit: int,
    ) -> list[SessionRunRecord]: ...

    async def delete_session(self, *, run_id: str) -> bool: ...


def run_result_event_type(status: str) -> str:
    if status == "interrupted":
        return "run.interrupted"
    return "run.completed"


class SqlAlchemyRunStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def claim_interrupted_resume(
        self,
        *,
        run_id: str,
        tenant_id: str,
        approval_id: str,
        claimed_by: str,
        runtime: RunResumeRuntime,
    ) -> bool:
        async with self._session_factory() as session:
            async with session.begin():
                claimed_run_id = await session.scalar(
                    build_claim_interrupted_run_resume_query(
                        run_id=run_id,
                        tenant_id=tenant_id,
                    )
                )
                if claimed_run_id is not None:
                    next_sequence = await session.scalar(
                        build_next_run_event_sequence_query(run_id=run_id)
                    )
                    session.add(
                        AgentRunEvent(
                            run_id=run_id,
                            tenant_id=tenant_id,
                            sequence=next_sequence or 1,
                            event_type="run.resume_claimed",
                            payload=resume_claim_event_payload(
                                approval_id=approval_id,
                                claimed_by=claimed_by,
                                runtime=runtime,
                            ),
                        )
                    )
        return claimed_run_id is not None

    async def record_started(
        self,
        *,
        run_id: str,
        tenant_id: str,
        user_id: str,
        thread_id: str,
        checkpoint_ns: str,
        input_text: str,
        metadata: Mapping[str, Any],
    ) -> str:
        queue_id = new_id("queue")
        async with self._session_factory() as session:
            async with session.begin():
                session.add(
                    AgentRun(
                        id=run_id,
                        tenant_id=tenant_id,
                        user_id=user_id,
                        thread_id=thread_id,
                        checkpoint_ns=checkpoint_ns,
                        status="running",
                        input_text=input_text,
                        run_metadata=dict(metadata),
                    )
                )
                session.add(
                    RunQueue(
                        id=queue_id,
                        run_id=run_id,
                        tenant_id=tenant_id,
                        status="leased",
                        lease_owner="api-inline",
                        fencing_token=1,
                        payload={"mode": "inline"},
                    )
                )
                session.add(
                    AgentRunEvent(
                        run_id=run_id,
                        tenant_id=tenant_id,
                        sequence=1,
                        event_type="run.created",
                        payload={"input_length": len(input_text), "queue_id": queue_id},
                    )
                )
        return queue_id

    async def record_completed(
        self,
        *,
        result: RunRecord,
        metadata: Mapping[str, Any],
        completion_events: Sequence[RunCompletionEvent] = (),
    ) -> bool:
        async with self._session_factory() as session:
            async with session.begin():
                transitioned_run_id = await session.scalar(
                    build_complete_running_run_query(
                        run_id=result.run_id,
                        tenant_id=result.tenant_id,
                        status=result.status,
                        response_text=result.response,
                        metadata=metadata,
                    )
                )
                if transitioned_run_id is None:
                    return False
                next_sequence = await session.scalar(
                    build_next_run_event_sequence_query(run_id=result.run_id)
                )
                await session.execute(
                    update(RunQueue)
                    .where(RunQueue.run_id == result.run_id)
                    .values(
                        status="completed",
                        lease_owner=None,
                        lease_expires_at=None,
                    )
                )
                first_sequence = next_sequence or 1
                session.add_all(
                    [
                        AgentRunEvent(
                            run_id=result.run_id,
                            tenant_id=result.tenant_id,
                            sequence=first_sequence,
                            event_type=run_result_event_type(result.status),
                            payload={"status": result.status},
                        ),
                        *[
                            AgentRunEvent(
                                run_id=result.run_id,
                                tenant_id=result.tenant_id,
                                sequence=first_sequence + offset,
                                event_type=event.event_type,
                                payload=dict(event.payload),
                            )
                            for offset, event in enumerate(completion_events, start=1)
                        ],
                    ]
                )
                return True

    async def record_cancelled_if_running(
        self,
        *,
        result: RunRecord,
        metadata: Mapping[str, Any],
    ) -> bool:
        return await self._record_cancelled(
            result=result,
            metadata=metadata,
            include_interrupted=False,
        )

    async def record_cancelled_if_active(
        self,
        *,
        result: RunRecord,
        metadata: Mapping[str, Any],
    ) -> bool:
        return await self._record_cancelled(
            result=result,
            metadata=metadata,
            include_interrupted=True,
        )

    async def _record_cancelled(
        self,
        *,
        result: RunRecord,
        metadata: Mapping[str, Any],
        include_interrupted: bool,
    ) -> bool:
        async with self._session_factory() as session:
            async with session.begin():
                cancelled_run_id = await session.scalar(
                    build_cancel_active_run_query(
                        run_id=result.run_id,
                        tenant_id=result.tenant_id,
                        response_text=result.response,
                        metadata=metadata,
                    )
                    if include_interrupted
                    else build_cancel_running_run_query(
                        run_id=result.run_id,
                        tenant_id=result.tenant_id,
                        response_text=result.response,
                        metadata=metadata,
                    )
                )
                if cancelled_run_id is None:
                    return False
                next_sequence = await session.scalar(
                    build_next_run_event_sequence_query(run_id=result.run_id)
                )
                await session.execute(
                    build_cancel_pending_run_approvals_query(
                        run_id=result.run_id,
                        tenant_id=result.tenant_id,
                        cancelled_by=result.user_id,
                        reason=str(metadata.get("cancel_reason") or "external_stream_cancellation"),
                    )
                )
                await session.execute(
                    build_cancel_pending_approval_tool_invocations_query(
                        run_id=result.run_id,
                        tenant_id=result.tenant_id,
                        reason=str(metadata.get("cancel_reason") or "external_stream_cancellation"),
                    )
                )
                await session.execute(
                    update(RunQueue)
                    .where(RunQueue.run_id == result.run_id)
                    .values(
                        status="completed",
                        lease_owner=None,
                        lease_expires_at=None,
                    )
                )
                session.add(
                    AgentRunEvent(
                        run_id=result.run_id,
                        tenant_id=result.tenant_id,
                        sequence=next_sequence or 1,
                        event_type="run.cancelled",
                        payload={
                            "status": result.status,
                            "cancelled_by": metadata.get("cancelled_by"),
                            "reason": metadata.get("cancel_reason"),
                        },
                    )
                )
        return True

    async def record_event(
        self,
        *,
        run_id: str,
        tenant_id: str,
        sequence: int,
        event_type: str,
        payload: Mapping[str, Any],
    ) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                session.add(
                    AgentRunEvent(
                        run_id=run_id,
                        tenant_id=tenant_id,
                        sequence=sequence,
                        event_type=event_type,
                        payload=dict(payload),
                    )
                )

    async def list_events(
        self,
        *,
        run_id: str,
        tenant_id: str | None = None,
        after_sequence: int = 0,
    ) -> list[RunEventRecord]:
        async with self._session_factory() as session:
            rows = await session.scalars(
                build_list_run_events_query(
                    run_id=run_id,
                    tenant_id=tenant_id,
                    after_sequence=after_sequence,
                )
            )
            return [
                RunEventRecord(
                    sequence=row.sequence,
                    event_type=row.event_type,
                    payload=row.payload,
                )
                for row in rows
            ]

    async def has_slack_thread_run(
        self,
        *,
        tenant_id: str,
        thread_id: str,
    ) -> bool:
        async with self._session_factory() as session:
            existing = await session.scalar(
                build_has_slack_thread_run_query(
                    tenant_id=tenant_id,
                    thread_id=thread_id,
                )
            )
            return existing is not None

    async def list_sessions(
        self,
        *,
        tenant_id: str,
        user_id: str | None,
        limit: int,
        offset: int,
    ) -> SessionListRecord:
        async with self._session_factory() as session:
            filters = [AgentRun.tenant_id == tenant_id]
            if user_id is not None:
                filters.append(AgentRun.user_id == user_id)
            total = await session.scalar(select(func.count()).select_from(AgentRun).where(*filters))
            rows = await session.scalars(
                select(AgentRun)
                .where(*filters)
                .order_by(AgentRun.updated_at.desc(), AgentRun.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            return SessionListRecord(
                items=[session_run_from_model(row) for row in rows],
                total=int(total or 0),
            )

    async def find_session(self, *, run_id: str) -> SessionRunRecord | None:
        async with self._session_factory() as session:
            row = await session.scalar(select(AgentRun).where(AgentRun.id == run_id))
            return session_run_from_model(row) if row is not None else None

    async def list_recent_runs(
        self,
        *,
        tenant_id: str,
        limit: int,
    ) -> list[SessionRunRecord]:
        async with self._session_factory() as session:
            rows = await session.scalars(
                select(AgentRun)
                .where(AgentRun.tenant_id == tenant_id)
                .order_by(AgentRun.updated_at.desc(), AgentRun.created_at.desc())
                .limit(max(0, min(limit, 500)))
            )
            return [session_run_from_model(row) for row in rows]

    async def delete_session(self, *, run_id: str) -> bool:
        async with self._session_factory() as session:
            async with session.begin():
                existing = await session.scalar(select(AgentRun.id).where(AgentRun.id == run_id))
                if existing is None:
                    return False
                await session.execute(delete(AgentRun).where(AgentRun.id == run_id))
                return True

    async def save_run(self, record: AgentRunMigrationRecord) -> str:
        record.validate()
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(build_agent_run_migration_upsert(record))
        return record.id

    async def save_run_event(self, record: AgentRunEventMigrationRecord) -> int | None:
        record.validate()
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(build_agent_run_event_migration_upsert(record))
        return record.id


def session_run_from_model(row: AgentRun) -> SessionRunRecord:
    return SessionRunRecord(
        run_id=row.id,
        tenant_id=row.tenant_id,
        user_id=row.user_id,
        thread_id=row.thread_id,
        checkpoint_ns=row.checkpoint_ns,
        status=row.status,
        input_text=row.input_text,
        response_text=row.response_text,
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
        metadata=row.run_metadata,
    )


def build_agent_run_migration_upsert(record: AgentRunMigrationRecord) -> Any:
    return (
        insert(AgentRun)
        .values(
            id=record.id,
            tenant_id=record.tenant_id,
            user_id=record.user_id,
            thread_id=record.thread_id,
            checkpoint_ns=record.checkpoint_ns,
            status=record.status,
            input_text=record.input_text,
            response_text=record.response_text,
            error_code=record.error_code,
            run_metadata=dict(record.metadata),
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
        .on_conflict_do_update(
            index_elements=[AgentRun.id],
            set_={
                "tenant_id": record.tenant_id,
                "user_id": record.user_id,
                "thread_id": record.thread_id,
                "checkpoint_ns": record.checkpoint_ns,
                "status": record.status,
                "input_text": record.input_text,
                "response_text": record.response_text,
                "error_code": record.error_code,
                "metadata": dict(record.metadata),
                "updated_at": record.updated_at,
            },
        )
    )


def build_list_run_events_query(
    *,
    run_id: str,
    tenant_id: str | None,
    after_sequence: int = 0,
) -> Select[tuple[AgentRunEvent]]:
    filters = [
        AgentRunEvent.run_id == run_id,
        AgentRunEvent.sequence > after_sequence,
    ]
    if tenant_id is not None:
        filters.append(AgentRunEvent.tenant_id == tenant_id)
    return select(AgentRunEvent).where(*filters).order_by(AgentRunEvent.sequence.asc())


def build_claim_interrupted_run_resume_query(*, run_id: str, tenant_id: str):
    return (
        update(AgentRun)
        .where(
            AgentRun.id == run_id,
            AgentRun.tenant_id == tenant_id,
            AgentRun.status == "interrupted",
        )
        .values(status="running")
        .returning(AgentRun.id)
    )


def build_complete_running_run_query(
    *,
    run_id: str,
    tenant_id: str,
    status: str,
    response_text: str,
    metadata: Mapping[str, Any],
):
    return (
        update(AgentRun)
        .where(
            AgentRun.id == run_id,
            AgentRun.tenant_id == tenant_id,
            AgentRun.status == "running",
        )
        .values(
            status=status,
            response_text=response_text,
            run_metadata=dict(metadata),
        )
        .returning(AgentRun.id)
    )


def build_cancel_running_run_query(
    *,
    run_id: str,
    tenant_id: str,
    response_text: str,
    metadata: Mapping[str, Any],
):
    return (
        update(AgentRun)
        .where(
            AgentRun.id == run_id,
            AgentRun.tenant_id == tenant_id,
            AgentRun.status == "running",
        )
        .values(
            status="cancelled",
            response_text=response_text,
            run_metadata=dict(metadata),
        )
        .returning(AgentRun.id)
    )


def build_cancel_active_run_query(
    *,
    run_id: str,
    tenant_id: str,
    response_text: str,
    metadata: Mapping[str, Any],
):
    return (
        update(AgentRun)
        .where(
            AgentRun.id == run_id,
            AgentRun.tenant_id == tenant_id,
            AgentRun.status.in_(("running", "interrupted")),
        )
        .values(
            status="cancelled",
            response_text=response_text,
            run_metadata=dict(metadata),
        )
        .returning(AgentRun.id)
    )


def build_cancel_pending_run_approvals_query(
    *,
    run_id: str,
    tenant_id: str,
    cancelled_by: str,
    reason: str,
):
    return (
        update(PendingApproval)
        .where(
            PendingApproval.run_id == run_id,
            PendingApproval.tenant_id == tenant_id,
            PendingApproval.status == PENDING_APPROVAL_STATUS,
        )
        .values(
            status=CANCELLED_APPROVAL_STATUS,
            decided_by=cancelled_by,
            decision_reason=reason,
            decided_at=func.now(),
        )
    )


def build_cancel_pending_approval_tool_invocations_query(
    *,
    run_id: str,
    tenant_id: str,
    reason: str,
):
    return (
        update(ToolInvocation)
        .where(
            ToolInvocation.run_id == run_id,
            ToolInvocation.tenant_id == tenant_id,
            ToolInvocation.status == "started",
            ToolInvocation.approval_id.is_(None),
            ToolInvocation.error_payload["error"]["code"].as_string() == "approval_required",
        )
        .values(
            status="cancelled",
            error_payload={
                "error": {
                    "code": "run_cancelled_before_approval",
                    "message": "tool invocation cancelled before approval",
                },
                "cancellation": {"reason": reason},
            },
            completed_at=func.now(),
        )
    )


def resume_claim_event_payload(
    *, approval_id: str, claimed_by: str, runtime: RunResumeRuntime
) -> dict[str, object]:
    return {
        "approval_id": approval_id,
        "claimed_by": claimed_by,
        "runtime": runtime,
    }


def build_next_run_event_sequence_query(*, run_id: str) -> Select[tuple[int]]:
    next_sequence = (func.coalesce(func.max(AgentRunEvent.sequence), 0) + 1).label("next_sequence")
    return select(next_sequence).where(AgentRunEvent.run_id == run_id)


def build_has_slack_thread_run_query(
    *,
    tenant_id: str,
    thread_id: str,
) -> Select[tuple[str]]:
    return (
        select(AgentRun.id)
        .where(
            AgentRun.tenant_id == tenant_id,
            AgentRun.thread_id == thread_id,
            AgentRun.run_metadata["source"].as_string() == "slack",
        )
        .limit(1)
    )


def build_agent_run_event_migration_upsert(record: AgentRunEventMigrationRecord) -> Any:
    values: dict[str, Any] = {
        "run_id": record.run_id,
        "tenant_id": record.tenant_id,
        "sequence": record.sequence,
        "event_type": record.event_type,
        "payload": dict(record.payload),
        "created_at": record.created_at,
    }
    if record.id is not None:
        values["id"] = record.id
    return (
        insert(AgentRunEvent)
        .values(values)
        .on_conflict_do_update(
            constraint="uq_agent_run_events_sequence",
            set_={
                "tenant_id": record.tenant_id,
                "event_type": record.event_type,
                "payload": dict(record.payload),
                "created_at": record.created_at,
            },
        )
    )


def require_non_blank(*fields: tuple[str, str]) -> None:
    for field_name, value in fields:
        if not value.strip():
            raise ValueError(f"{field_name} is required")
