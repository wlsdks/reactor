from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import Select, and_, func, literal, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reactor.kernel.ids import new_id
from reactor.persistence.models import (
    DeadLetterJob,
    IdempotencyRecord,
    InboxEvent,
    OutboxEvent,
    RunQueue,
)


def build_claim_queue_query(tenant_id: str, limit: int) -> Select[tuple[RunQueue]]:
    return (
        select(RunQueue)
        .where(
            RunQueue.tenant_id == tenant_id,
            RunQueue.status.in_(["queued", "retryable_failed"]),
            RunQueue.available_at <= datetime.now().astimezone(),
        )
        .order_by(RunQueue.priority.asc(), RunQueue.available_at.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    )


def build_durable_queue_diagnostics_query(tenant_id: str) -> Any:
    queue_counts = (
        select(
            RunQueue.status.label("queue_status"),
            func.count(RunQueue.id).label("queue_count"),
            literal(0).label("dead_letter_count"),
        )
        .where(RunQueue.tenant_id == tenant_id)
        .group_by(RunQueue.status)
    )
    dead_letter_counts = (
        select(
            literal("dead_lettered").label("queue_status"),
            literal(0).label("queue_count"),
            func.count(DeadLetterJob.id).label("dead_letter_count"),
        )
        .where(DeadLetterJob.tenant_id == tenant_id)
        .group_by(literal("dead_lettered"))
    )
    return queue_counts.union_all(dead_letter_counts)


def build_claim_outbox_query(tenant_id: str, limit: int) -> Select[tuple[OutboxEvent]]:
    now = datetime.now().astimezone()
    return (
        select(OutboxEvent)
        .where(
            OutboxEvent.tenant_id == tenant_id,
            or_(
                and_(
                    OutboxEvent.status.in_(["pending", "retryable_failed"]),
                    OutboxEvent.available_at <= now,
                ),
                and_(
                    OutboxEvent.status == "dispatching",
                    OutboxEvent.lease_expires_at <= now,
                ),
            ),
        )
        .order_by(OutboxEvent.available_at.asc(), OutboxEvent.created_at.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    )


def build_retry_expired_run_queue_statement(tenant_id: str) -> Any:
    now = datetime.now().astimezone()
    return (
        update(RunQueue)
        .where(
            RunQueue.tenant_id == tenant_id,
            RunQueue.status == "leased",
            RunQueue.lease_expires_at < now,
            RunQueue.attempt < RunQueue.max_attempts,
        )
        .values(
            status="retryable_failed",
            lease_owner=None,
            lease_expires_at=None,
        )
        .returning(RunQueue.id)
    )


def build_dead_letter_expired_run_queue_statement(tenant_id: str) -> Any:
    now = datetime.now().astimezone()
    return (
        update(RunQueue)
        .where(
            RunQueue.tenant_id == tenant_id,
            RunQueue.status == "leased",
            RunQueue.lease_expires_at < now,
            RunQueue.attempt >= RunQueue.max_attempts,
        )
        .values(
            status="dead_lettered",
            lease_owner=None,
            lease_expires_at=None,
        )
        .returning(RunQueue.id)
    )


def build_expired_run_queue_dead_letter_query(tenant_id: str) -> Select[tuple[RunQueue]]:
    now = datetime.now().astimezone()
    return (
        select(RunQueue)
        .where(
            RunQueue.tenant_id == tenant_id,
            RunQueue.status == "leased",
            RunQueue.lease_expires_at < now,
            RunQueue.attempt >= RunQueue.max_attempts,
        )
        .with_for_update(skip_locked=True)
    )


def dead_letter_job_from_expired_run_queue(queue: RunQueue) -> DeadLetterJob:
    checkpoint_id = string_payload_value(queue.payload, "checkpointId")
    trace_id = string_payload_value(queue.payload, "traceId")
    return DeadLetterJob(
        id=new_id("dead"),
        queue_id=queue.id,
        run_id=queue.run_id,
        tenant_id=queue.tenant_id,
        reason="run_queue_lease_attempts_exhausted",
        last_checkpoint_id=checkpoint_id,
        trace_id=trace_id,
        payload={
            "attempt": queue.attempt,
            "maxAttempts": queue.max_attempts,
            "leaseOwner": queue.lease_owner,
            "leaseExpiresAt": queue.lease_expires_at.isoformat()
            if queue.lease_expires_at is not None
            else None,
            "fencingToken": queue.fencing_token,
            "queuePayload": dict(queue.payload),
        },
    )


def string_payload_value(payload: Mapping[str, Any], key: str) -> str | None:
    value = payload.get(key)
    return value if isinstance(value, str) and value.strip() else None


@dataclass(frozen=True)
class OutboxRequest:
    tenant_id: str
    destination: str
    event_type: str
    idempotency_key: str
    payload: Mapping[str, Any]
    run_id: str | None = None
    max_attempts: int = 5


@dataclass(frozen=True)
class OutboxLease:
    event_id: str
    tenant_id: str
    destination: str
    event_type: str
    attempt: int
    max_attempts: int
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class RunQueueLease:
    queue_id: str
    run_id: str
    tenant_id: str
    lease_owner: str
    fencing_token: int
    lease_expires_at: datetime
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class RunQueueMigrationRecord:
    id: str
    run_id: str
    tenant_id: str
    status: str
    priority: int
    attempt: int
    max_attempts: int
    available_at: datetime
    lease_owner: str | None
    lease_expires_at: datetime | None
    fencing_token: int
    payload: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    def validate(self) -> None:
        require_non_blank(
            ("id", self.id),
            ("run_id", self.run_id),
            ("tenant_id", self.tenant_id),
            ("status", self.status),
        )


@dataclass(frozen=True)
class DeadLetterJobMigrationRecord:
    id: str
    queue_id: str
    run_id: str
    tenant_id: str
    reason: str
    last_checkpoint_id: str | None
    trace_id: str | None
    payload: dict[str, Any]
    created_at: datetime

    def validate(self) -> None:
        require_non_blank(
            ("id", self.id),
            ("queue_id", self.queue_id),
            ("run_id", self.run_id),
            ("tenant_id", self.tenant_id),
            ("reason", self.reason),
        )


@dataclass(frozen=True)
class IdempotencyMigrationRecord:
    key: str
    tenant_id: str
    scope: str
    request_checksum: str
    status: str
    response_payload: dict[str, Any] | None
    locked_until: datetime | None
    created_at: datetime
    updated_at: datetime

    def validate(self) -> None:
        require_non_blank(
            ("key", self.key),
            ("tenant_id", self.tenant_id),
            ("scope", self.scope),
            ("request_checksum", self.request_checksum),
            ("status", self.status),
        )


@dataclass(frozen=True)
class OutboxEventMigrationRecord:
    id: str
    tenant_id: str
    run_id: str | None
    destination: str
    event_type: str
    idempotency_key: str
    status: str
    attempt: int
    max_attempts: int
    available_at: datetime
    payload: dict[str, Any]
    last_error: str | None
    lease_owner: str | None
    lease_expires_at: datetime | None
    created_at: datetime
    updated_at: datetime

    def validate(self) -> None:
        require_non_blank(
            ("id", self.id),
            ("tenant_id", self.tenant_id),
            ("destination", self.destination),
            ("event_type", self.event_type),
            ("idempotency_key", self.idempotency_key),
            ("status", self.status),
        )


@dataclass(frozen=True)
class InboxEventMigrationRecord:
    id: str
    tenant_id: str
    source: str
    source_event_id: str
    event_type: str
    status: str
    payload: dict[str, Any]
    received_at: datetime
    processed_at: datetime | None

    def validate(self) -> None:
        require_non_blank(
            ("id", self.id),
            ("tenant_id", self.tenant_id),
            ("source", self.source),
            ("source_event_id", self.source_event_id),
            ("event_type", self.event_type),
            ("status", self.status),
        )


class DurableStore(Protocol):
    async def start_idempotency(
        self,
        *,
        key: str,
        tenant_id: str,
        scope: str,
        request_checksum: str,
    ) -> bool: ...

    async def enqueue_outbox(self, request: OutboxRequest) -> str: ...

    async def claim_outbox(
        self,
        *,
        tenant_id: str,
        lease_owner: str,
        limit: int = 10,
    ) -> list[OutboxLease]: ...

    async def mark_outbox_dispatched(self, *, event_id: str, lease_owner: str) -> None: ...

    async def mark_outbox_failed(
        self,
        *,
        event_id: str,
        lease_owner: str,
        status: str,
        error: str,
        retry_after_seconds: int | None = None,
    ) -> None: ...

    async def claim_run_queue(
        self,
        *,
        tenant_id: str,
        lease_owner: str,
        lease_seconds: int,
        limit: int = 1,
    ) -> list[RunQueueLease]: ...

    async def heartbeat_run_queue(
        self,
        *,
        queue_id: str,
        lease_owner: str,
        fencing_token: int,
        lease_seconds: int,
    ) -> bool: ...

    async def release_expired_run_queue(self, *, tenant_id: str) -> int: ...

    async def durable_queue_diagnostics(self, *, tenant_id: str) -> list[dict[str, object]]: ...


class SqlAlchemyDurableStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def start_idempotency(
        self,
        *,
        key: str,
        tenant_id: str,
        scope: str,
        request_checksum: str,
    ) -> bool:
        statement = (
            insert(IdempotencyRecord)
            .values(
                key=key,
                tenant_id=tenant_id,
                scope=scope,
                request_checksum=request_checksum,
                status="started",
            )
            .on_conflict_do_nothing(index_elements=[IdempotencyRecord.key])
            .returning(IdempotencyRecord.key)
        )
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.scalar(statement)
        return result == key

    async def enqueue_outbox(self, request: OutboxRequest) -> str:
        event_id = new_id("outbox")
        statement = (
            insert(OutboxEvent)
            .values(
                id=event_id,
                tenant_id=request.tenant_id,
                run_id=request.run_id,
                destination=request.destination,
                event_type=request.event_type,
                idempotency_key=request.idempotency_key,
                status="pending",
                max_attempts=request.max_attempts,
                payload=dict(request.payload),
            )
            .on_conflict_do_nothing(
                constraint="uq_outbox_events_idempotency",
            )
            .returning(OutboxEvent.id)
        )
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.scalar(statement)
                if result is not None:
                    return result
                existing = await session.scalar(
                    select(OutboxEvent.id).where(
                        OutboxEvent.tenant_id == request.tenant_id,
                        OutboxEvent.idempotency_key == request.idempotency_key,
                    )
                )
        return existing or event_id

    async def claim_outbox(
        self,
        *,
        tenant_id: str,
        lease_owner: str,
        limit: int = 10,
    ) -> list[OutboxLease]:
        lease_expires_at = datetime.now().astimezone() + timedelta(minutes=5)
        leases: list[OutboxLease] = []
        async with self._session_factory() as session:
            async with session.begin():
                rows = await session.scalars(build_claim_outbox_query(tenant_id, limit))
                events = list(rows)
                for event in events:
                    event.status = "dispatching"
                    event.lease_owner = lease_owner
                    event.lease_expires_at = lease_expires_at
                    event.attempt += 1
                    event.last_error = None
                    leases.append(
                        OutboxLease(
                            event_id=event.id,
                            tenant_id=event.tenant_id,
                            destination=event.destination,
                            event_type=event.event_type,
                            attempt=event.attempt,
                            max_attempts=event.max_attempts,
                            payload=event.payload,
                        )
                    )
        return leases

    async def mark_outbox_dispatched(self, *, event_id: str, lease_owner: str) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(
                    update(OutboxEvent)
                    .where(
                        OutboxEvent.id == event_id,
                        OutboxEvent.status == "dispatching",
                        OutboxEvent.lease_owner == lease_owner,
                    )
                    .values(
                        status="dispatched",
                        last_error=None,
                        lease_owner=None,
                        lease_expires_at=None,
                    )
                )

    async def mark_outbox_failed(
        self,
        *,
        event_id: str,
        lease_owner: str,
        status: str,
        error: str,
        retry_after_seconds: int | None = None,
    ) -> None:
        if status not in {"retryable_failed", "dead_lettered"}:
            raise ValueError("outbox failure status must be retryable_failed or dead_lettered")
        retry_delay_seconds = retry_after_seconds if retry_after_seconds is not None else 30
        available_at = datetime.now().astimezone() + timedelta(seconds=retry_delay_seconds)
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(
                    update(OutboxEvent)
                    .where(
                        OutboxEvent.id == event_id,
                        OutboxEvent.status == "dispatching",
                        OutboxEvent.lease_owner == lease_owner,
                    )
                    .values(
                        status=status,
                        last_error=error[:1000],
                        available_at=available_at,
                        lease_owner=None,
                        lease_expires_at=None,
                    )
                )

    async def claim_run_queue(
        self,
        *,
        tenant_id: str,
        lease_owner: str,
        lease_seconds: int,
        limit: int = 1,
    ) -> list[RunQueueLease]:
        now = datetime.now().astimezone()
        lease_expires_at = now + timedelta(seconds=lease_seconds)
        leases: list[RunQueueLease] = []

        async with self._session_factory() as session:
            async with session.begin():
                rows = await session.scalars(build_claim_queue_query(tenant_id, limit))
                queued_items = list(rows)
                for item in queued_items:
                    item.status = "leased"
                    item.lease_owner = lease_owner
                    item.lease_expires_at = lease_expires_at
                    item.attempt += 1
                    item.fencing_token += 1
                    leases.append(
                        RunQueueLease(
                            queue_id=item.id,
                            run_id=item.run_id,
                            tenant_id=item.tenant_id,
                            lease_owner=lease_owner,
                            fencing_token=item.fencing_token,
                            lease_expires_at=lease_expires_at,
                            payload=item.payload,
                        )
                    )
        return leases

    async def heartbeat_run_queue(
        self,
        *,
        queue_id: str,
        lease_owner: str,
        fencing_token: int,
        lease_seconds: int,
    ) -> bool:
        lease_expires_at = datetime.now().astimezone() + timedelta(seconds=lease_seconds)
        statement = (
            update(RunQueue)
            .where(
                RunQueue.id == queue_id,
                RunQueue.status == "leased",
                RunQueue.lease_owner == lease_owner,
                RunQueue.fencing_token == fencing_token,
            )
            .values(lease_expires_at=lease_expires_at)
            .returning(RunQueue.id)
        )
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.scalar(statement)
        return result == queue_id

    async def release_expired_run_queue(self, *, tenant_id: str) -> int:
        async with self._session_factory() as session:
            async with session.begin():
                dead_letter_candidates = list(
                    await session.scalars(build_expired_run_queue_dead_letter_query(tenant_id))
                )
                session.add_all(
                    [
                        dead_letter_job_from_expired_run_queue(queue)
                        for queue in dead_letter_candidates
                    ]
                )
                retry_rows = await session.scalars(
                    build_retry_expired_run_queue_statement(tenant_id)
                )
                dead_letter_rows = await session.scalars(
                    build_dead_letter_expired_run_queue_statement(tenant_id)
                )
                released = [*retry_rows, *dead_letter_rows]
        return len(released)

    async def durable_queue_diagnostics(self, *, tenant_id: str) -> list[dict[str, object]]:
        async with self._session_factory() as session:
            result = await session.execute(build_durable_queue_diagnostics_query(tenant_id))
            rows = result.mappings().all()
        return [
            {
                "queue_status": str(row["queue_status"]),
                "queue_count": int(row["queue_count"]),
                "dead_letter_count": int(row["dead_letter_count"]),
            }
            for row in rows
        ]

    async def save_run_queue(self, record: RunQueueMigrationRecord) -> str:
        record.validate()
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(build_run_queue_migration_upsert(record))
        return record.id

    async def save_dead_letter_job(self, record: DeadLetterJobMigrationRecord) -> str:
        record.validate()
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(build_dead_letter_job_migration_upsert(record))
        return record.id

    async def save_idempotency_record(self, record: IdempotencyMigrationRecord) -> str:
        record.validate()
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(build_idempotency_migration_upsert(record))
        return record.key

    async def save_outbox_event(self, record: OutboxEventMigrationRecord) -> str:
        record.validate()
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(build_outbox_event_migration_upsert(record))
        return record.id

    async def save_inbox_event(self, record: InboxEventMigrationRecord) -> str:
        record.validate()
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(build_inbox_event_migration_upsert(record))
        return record.id


def build_run_queue_migration_upsert(record: RunQueueMigrationRecord) -> Any:
    return (
        insert(RunQueue)
        .values(
            id=record.id,
            run_id=record.run_id,
            tenant_id=record.tenant_id,
            status=record.status,
            priority=record.priority,
            attempt=record.attempt,
            max_attempts=record.max_attempts,
            available_at=record.available_at,
            lease_owner=record.lease_owner,
            lease_expires_at=record.lease_expires_at,
            fencing_token=record.fencing_token,
            payload=dict(record.payload),
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
        .on_conflict_do_update(
            index_elements=[RunQueue.id],
            set_={
                "status": record.status,
                "priority": record.priority,
                "attempt": record.attempt,
                "max_attempts": record.max_attempts,
                "available_at": record.available_at,
                "lease_owner": record.lease_owner,
                "lease_expires_at": record.lease_expires_at,
                "fencing_token": record.fencing_token,
                "payload": dict(record.payload),
                "updated_at": record.updated_at,
            },
        )
    )


def build_dead_letter_job_migration_upsert(record: DeadLetterJobMigrationRecord) -> Any:
    return (
        insert(DeadLetterJob)
        .values(
            id=record.id,
            queue_id=record.queue_id,
            run_id=record.run_id,
            tenant_id=record.tenant_id,
            reason=record.reason,
            last_checkpoint_id=record.last_checkpoint_id,
            trace_id=record.trace_id,
            payload=dict(record.payload),
            created_at=record.created_at,
        )
        .on_conflict_do_update(
            index_elements=[DeadLetterJob.id],
            set_={
                "reason": record.reason,
                "last_checkpoint_id": record.last_checkpoint_id,
                "trace_id": record.trace_id,
                "payload": dict(record.payload),
            },
        )
    )


def build_idempotency_migration_upsert(record: IdempotencyMigrationRecord) -> Any:
    return (
        insert(IdempotencyRecord)
        .values(
            key=record.key,
            tenant_id=record.tenant_id,
            scope=record.scope,
            request_checksum=record.request_checksum,
            status=record.status,
            response_payload=record.response_payload,
            locked_until=record.locked_until,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
        .on_conflict_do_update(
            index_elements=[IdempotencyRecord.key],
            set_={
                "status": record.status,
                "response_payload": record.response_payload,
                "locked_until": record.locked_until,
                "updated_at": record.updated_at,
            },
        )
    )


def build_outbox_event_migration_upsert(record: OutboxEventMigrationRecord) -> Any:
    return (
        insert(OutboxEvent)
        .values(
            id=record.id,
            tenant_id=record.tenant_id,
            run_id=record.run_id,
            destination=record.destination,
            event_type=record.event_type,
            idempotency_key=record.idempotency_key,
            status=record.status,
            attempt=record.attempt,
            max_attempts=record.max_attempts,
            available_at=record.available_at,
            payload=dict(record.payload),
            last_error=record.last_error,
            lease_owner=record.lease_owner,
            lease_expires_at=record.lease_expires_at,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
        .on_conflict_do_update(
            constraint="uq_outbox_events_idempotency",
            set_={
                "status": record.status,
                "attempt": record.attempt,
                "max_attempts": record.max_attempts,
                "available_at": record.available_at,
                "payload": dict(record.payload),
                "last_error": record.last_error,
                "lease_owner": record.lease_owner,
                "lease_expires_at": record.lease_expires_at,
                "updated_at": record.updated_at,
            },
        )
    )


def build_inbox_event_migration_upsert(record: InboxEventMigrationRecord) -> Any:
    return (
        insert(InboxEvent)
        .values(
            id=record.id,
            tenant_id=record.tenant_id,
            source=record.source,
            source_event_id=record.source_event_id,
            event_type=record.event_type,
            status=record.status,
            payload=dict(record.payload),
            received_at=record.received_at,
            processed_at=record.processed_at,
        )
        .on_conflict_do_update(
            constraint="uq_inbox_events_source_event",
            set_={
                "event_type": record.event_type,
                "status": record.status,
                "payload": dict(record.payload),
                "received_at": record.received_at,
                "processed_at": record.processed_at,
            },
        )
    )


def require_non_blank(*fields: tuple[str, str]) -> None:
    for field_name, value in fields:
        if not value.strip():
            raise ValueError(f"{field_name} is required")
