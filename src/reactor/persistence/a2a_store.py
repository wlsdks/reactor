from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, cast

from sqlalchemy import case, delete, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reactor.a2a.access_policy import A2AAccessPolicyDraft, A2AAccessPolicyView
from reactor.a2a.peers import A2APeerDraft, A2APeerRecord
from reactor.a2a.tasks import A2ATaskDraft, A2ATaskRecord, build_a2a_push_outbox_request
from reactor.kernel.ids import new_id
from reactor.persistence.durable_store import DurableStore
from reactor.persistence.models import (
    A2AAccessPolicy,
    A2AAgentCard,
    A2APeerAgent,
    A2APushSubscription,
    A2ATask,
    A2ATaskEvent,
)


@dataclass(frozen=True)
class A2APeerAgentRecord:
    id: str
    tenant_id: str
    name: str
    endpoint_url: str
    agent_card: dict[str, Any]
    enabled: bool
    created_at: datetime
    updated_at: datetime

    def validate(self) -> None:
        require_non_blank(
            ("id", self.id),
            ("tenant_id", self.tenant_id),
            ("name", self.name),
            ("endpoint_url", self.endpoint_url),
        )


@dataclass(frozen=True)
class A2AAgentCardRecord:
    id: str
    tenant_id: str
    version: str
    protocol_version: str
    card: dict[str, Any]
    active: bool
    created_at: datetime

    def validate(self) -> None:
        require_non_blank(
            ("id", self.id),
            ("tenant_id", self.tenant_id),
            ("version", self.version),
            ("protocol_version", self.protocol_version),
        )


@dataclass(frozen=True)
class A2ATaskMigrationRecord:
    id: str
    tenant_id: str
    peer_agent_id: str | None
    run_id: str
    thread_id: str
    session_id: str
    context_id: str
    message_id: str
    status: str
    idempotency_key: str
    input_payload: dict[str, Any]
    output_payload: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime

    def validate(self) -> None:
        require_non_blank(
            ("id", self.id),
            ("tenant_id", self.tenant_id),
            ("run_id", self.run_id),
            ("thread_id", self.thread_id),
            ("session_id", self.session_id),
            ("context_id", self.context_id),
            ("message_id", self.message_id),
            ("status", self.status),
            ("idempotency_key", self.idempotency_key),
        )


@dataclass(frozen=True)
class A2ATaskEventRecord:
    id: str
    task_id: str
    tenant_id: str
    sequence: int
    event_type: str
    payload: dict[str, Any]
    created_at: datetime

    def validate(self) -> None:
        require_non_blank(
            ("id", self.id),
            ("task_id", self.task_id),
            ("tenant_id", self.tenant_id),
            ("event_type", self.event_type),
        )


@dataclass(frozen=True)
class A2APushSubscriptionRecord:
    id: str
    tenant_id: str
    destination: str
    signing_key_ref: str | None
    enabled: bool
    created_at: datetime

    def validate(self) -> None:
        require_non_blank(
            ("id", self.id),
            ("tenant_id", self.tenant_id),
            ("destination", self.destination),
        )


@dataclass(frozen=True)
class A2AAccessPolicyRecord:
    id: str
    tenant_id: str
    peer_agent_id: str | None
    allow_inbound: bool
    allow_outbound: bool
    allowed_skills: list[str]
    created_at: datetime

    def validate(self) -> None:
        require_non_blank(("id", self.id), ("tenant_id", self.tenant_id))


def require_non_blank(*fields: tuple[str, str]) -> None:
    for field_name, value in fields:
        if not value.strip():
            raise ValueError(f"{field_name} is required")


def build_a2a_peer_agent_record_upsert(record: A2APeerAgentRecord):
    return (
        insert(A2APeerAgent)
        .values(
            id=record.id,
            tenant_id=record.tenant_id,
            name=record.name,
            endpoint_url=record.endpoint_url,
            agent_card=record.agent_card,
            enabled=record.enabled,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
        .on_conflict_do_update(
            constraint="uq_a2a_peer_agents_name",
            set_={
                "endpoint_url": record.endpoint_url,
                "agent_card": record.agent_card,
                "enabled": record.enabled,
                "updated_at": record.updated_at,
            },
        )
    )


def build_a2a_agent_card_record_upsert(record: A2AAgentCardRecord):
    return (
        insert(A2AAgentCard)
        .values(
            id=record.id,
            tenant_id=record.tenant_id,
            version=record.version,
            protocol_version=record.protocol_version,
            card=record.card,
            active=record.active,
            created_at=record.created_at,
        )
        .on_conflict_do_update(
            constraint="uq_a2a_agent_cards_version",
            set_={
                "protocol_version": record.protocol_version,
                "card": record.card,
                "active": record.active,
            },
        )
    )


def build_a2a_task_record_upsert(record: A2ATaskMigrationRecord):
    return (
        insert(A2ATask)
        .values(
            id=record.id,
            tenant_id=record.tenant_id,
            peer_agent_id=record.peer_agent_id,
            run_id=record.run_id,
            thread_id=record.thread_id,
            session_id=record.session_id,
            context_id=record.context_id,
            message_id=record.message_id,
            status=record.status,
            idempotency_key=record.idempotency_key,
            input_payload=record.input_payload,
            output_payload=record.output_payload,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
        .on_conflict_do_update(
            constraint="uq_a2a_tasks_idempotency",
            set_={
                "peer_agent_id": record.peer_agent_id,
                "run_id": record.run_id,
                "thread_id": record.thread_id,
                "session_id": record.session_id,
                "context_id": record.context_id,
                "message_id": record.message_id,
                "status": record.status,
                "input_payload": record.input_payload,
                "output_payload": record.output_payload,
                "updated_at": record.updated_at,
            },
        )
    )


def build_a2a_task_event_record_upsert(record: A2ATaskEventRecord):
    return (
        insert(A2ATaskEvent)
        .values(
            id=record.id,
            task_id=record.task_id,
            tenant_id=record.tenant_id,
            sequence=record.sequence,
            event_type=record.event_type,
            payload=record.payload,
            created_at=record.created_at,
        )
        .on_conflict_do_update(
            constraint="uq_a2a_task_events_sequence",
            set_={
                "event_type": record.event_type,
                "payload": record.payload,
                "created_at": record.created_at,
            },
        )
    )


def build_a2a_push_subscription_record_upsert(record: A2APushSubscriptionRecord):
    return (
        insert(A2APushSubscription)
        .values(
            id=record.id,
            tenant_id=record.tenant_id,
            destination=record.destination,
            signing_key_ref=record.signing_key_ref,
            enabled=record.enabled,
            created_at=record.created_at,
        )
        .on_conflict_do_update(
            constraint="uq_a2a_push_subscriptions_destination",
            set_={
                "signing_key_ref": record.signing_key_ref,
                "enabled": record.enabled,
            },
        )
    )


def build_a2a_access_policy_record_upsert(record: A2AAccessPolicyRecord):
    return (
        insert(A2AAccessPolicy)
        .values(
            id=record.id,
            tenant_id=record.tenant_id,
            peer_agent_id=record.peer_agent_id,
            allow_inbound=record.allow_inbound,
            allow_outbound=record.allow_outbound,
            allowed_skills=record.allowed_skills,
            created_at=record.created_at,
        )
        .on_conflict_do_update(
            constraint="uq_a2a_access_policy",
            set_={
                "allow_inbound": record.allow_inbound,
                "allow_outbound": record.allow_outbound,
                "allowed_skills": record.allowed_skills,
            },
        )
    )


class A2ATaskStore(Protocol):
    async def create_task(self, draft: A2ATaskDraft) -> A2ATaskRecord: ...

    async def is_outbound_allowed(
        self,
        *,
        tenant_id: str,
        peer_agent_id: str | None,
    ) -> bool: ...

    async def is_inbound_allowed(
        self,
        *,
        tenant_id: str,
        peer_agent_id: str | None,
    ) -> bool: ...

    async def is_skill_allowed(
        self,
        *,
        tenant_id: str,
        peer_agent_id: str | None,
        skill_id: str | None,
    ) -> bool: ...

    async def get_access_policy(
        self,
        *,
        tenant_id: str,
        peer_agent_id: str | None,
    ) -> A2AAccessPolicyView | None: ...

    async def save_access_policy_draft(
        self,
        draft: A2AAccessPolicyDraft,
    ) -> A2AAccessPolicyView: ...

    async def get_task(self, *, tenant_id: str, task_id: str) -> A2ATaskRecord | None: ...

    async def list_task_events(
        self,
        *,
        tenant_id: str,
        task_id: str,
    ) -> list[dict[str, object]] | None: ...

    async def save_sdk_task(
        self,
        *,
        tenant_id: str,
        task_id: str,
        context_id: str,
        status: str,
        payload: dict[str, object],
    ) -> None: ...

    async def get_sdk_task(self, *, tenant_id: str, task_id: str) -> dict[str, object] | None: ...

    async def list_sdk_tasks(
        self,
        *,
        tenant_id: str,
        context_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, object]]: ...

    async def delete_sdk_task(self, *, tenant_id: str, task_id: str) -> None: ...


class A2APeerStore(Protocol):
    async def register_peer(self, draft: A2APeerDraft) -> A2APeerRecord: ...

    async def list_peers(self, *, tenant_id: str) -> list[A2APeerRecord]: ...


class SqlAlchemyA2ATaskStore:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        durable_store: DurableStore | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._durable_store = durable_store

    async def register_peer(self, draft: A2APeerDraft) -> A2APeerRecord:
        statement = (
            insert(A2APeerAgent)
            .values(
                id=draft.peer_agent_id,
                tenant_id=draft.tenant_id,
                name=draft.name,
                endpoint_url=draft.endpoint_url,
                agent_card=dict(draft.agent_card),
                enabled=draft.enabled,
            )
            .on_conflict_do_update(
                constraint="uq_a2a_peer_agents_name",
                set_={
                    "endpoint_url": draft.endpoint_url,
                    "agent_card": dict(draft.agent_card),
                    "enabled": draft.enabled,
                },
            )
            .returning(A2APeerAgent)
        )
        async with self._session_factory() as session:
            async with session.begin():
                peer = await session.scalar(statement)
                if peer is None:
                    raise RuntimeError("A2A peer upsert did not return a row")
        return self._peer_record(peer)

    async def save_peer_agent(self, record: A2APeerAgentRecord) -> A2APeerAgentRecord:
        record.validate()
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(build_a2a_peer_agent_record_upsert(record))
        return record

    async def save_agent_card(self, record: A2AAgentCardRecord) -> A2AAgentCardRecord:
        record.validate()
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(build_a2a_agent_card_record_upsert(record))
        return record

    async def save_task(self, record: A2ATaskMigrationRecord) -> A2ATaskMigrationRecord:
        record.validate()
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(build_a2a_task_record_upsert(record))
        return record

    async def save_task_event(self, record: A2ATaskEventRecord) -> A2ATaskEventRecord:
        record.validate()
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(build_a2a_task_event_record_upsert(record))
        return record

    async def save_push_subscription(
        self,
        record: A2APushSubscriptionRecord,
    ) -> A2APushSubscriptionRecord:
        record.validate()
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(build_a2a_push_subscription_record_upsert(record))
        return record

    async def save_access_policy(self, record: A2AAccessPolicyRecord) -> A2AAccessPolicyRecord:
        record.validate()
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(build_a2a_access_policy_record_upsert(record))
        return record

    async def save_access_policy_draft(
        self,
        draft: A2AAccessPolicyDraft,
    ) -> A2AAccessPolicyView:
        record = A2AAccessPolicyRecord(
            id=draft.policy_id,
            tenant_id=draft.tenant_id,
            peer_agent_id=draft.peer_agent_id,
            allow_inbound=draft.allow_inbound,
            allow_outbound=draft.allow_outbound,
            allowed_skills=draft.allowed_skills,
            created_at=datetime.now().astimezone(),
        )
        saved = await self.save_access_policy(record)
        return A2AAccessPolicyView(
            tenant_id=saved.tenant_id,
            peer_agent_id=saved.peer_agent_id,
            allow_inbound=saved.allow_inbound,
            allow_outbound=saved.allow_outbound,
            allowed_skills=saved.allowed_skills,
        )

    async def list_peers(self, *, tenant_id: str) -> list[A2APeerRecord]:
        async with self._session_factory() as session:
            rows = await session.scalars(
                select(A2APeerAgent)
                .where(A2APeerAgent.tenant_id == tenant_id)
                .order_by(A2APeerAgent.name.asc())
            )
            peers = list(rows)
        return [self._peer_record(peer) for peer in peers]

    async def get_access_policy(
        self,
        *,
        tenant_id: str,
        peer_agent_id: str | None,
    ) -> A2AAccessPolicyView | None:
        async with self._session_factory() as session:
            policy = await session.scalar(
                select(A2AAccessPolicy).where(
                    A2AAccessPolicy.tenant_id == tenant_id,
                    A2AAccessPolicy.peer_agent_id == peer_agent_id,
                )
            )
        if policy is None:
            return None
        return A2AAccessPolicyView(
            tenant_id=policy.tenant_id,
            peer_agent_id=policy.peer_agent_id,
            allow_inbound=policy.allow_inbound,
            allow_outbound=policy.allow_outbound,
            allowed_skills=policy.allowed_skills,
        )

    async def is_outbound_allowed(
        self,
        *,
        tenant_id: str,
        peer_agent_id: str | None,
    ) -> bool:
        statement = (
            select(A2AAccessPolicy.allow_outbound)
            .where(
                A2AAccessPolicy.tenant_id == tenant_id,
                or_(
                    A2AAccessPolicy.peer_agent_id == peer_agent_id,
                    A2AAccessPolicy.peer_agent_id.is_(None),
                ),
            )
            .order_by(case((A2AAccessPolicy.peer_agent_id == peer_agent_id, 0), else_=1))
            .limit(1)
        )
        async with self._session_factory() as session:
            allowed = await session.scalar(statement)
        return True if allowed is None else bool(allowed)

    async def is_inbound_allowed(
        self,
        *,
        tenant_id: str,
        peer_agent_id: str | None,
    ) -> bool:
        statement = (
            select(A2AAccessPolicy.allow_inbound)
            .where(
                A2AAccessPolicy.tenant_id == tenant_id,
                or_(
                    A2AAccessPolicy.peer_agent_id == peer_agent_id,
                    A2AAccessPolicy.peer_agent_id.is_(None),
                ),
            )
            .order_by(case((A2AAccessPolicy.peer_agent_id == peer_agent_id, 0), else_=1))
            .limit(1)
        )
        async with self._session_factory() as session:
            allowed = await session.scalar(statement)
        return True if allowed is None else bool(allowed)

    async def is_skill_allowed(
        self,
        *,
        tenant_id: str,
        peer_agent_id: str | None,
        skill_id: str | None,
    ) -> bool:
        if skill_id is None:
            return True
        statement = (
            select(A2AAccessPolicy.allowed_skills)
            .where(
                A2AAccessPolicy.tenant_id == tenant_id,
                or_(
                    A2AAccessPolicy.peer_agent_id == peer_agent_id,
                    A2AAccessPolicy.peer_agent_id.is_(None),
                ),
            )
            .order_by(case((A2AAccessPolicy.peer_agent_id == peer_agent_id, 0), else_=1))
            .limit(1)
        )
        async with self._session_factory() as session:
            allowed_skills = await session.scalar(statement)
        if not allowed_skills:
            return True
        return skill_id in allowed_skills

    async def create_task(self, draft: A2ATaskDraft) -> A2ATaskRecord:
        idempotency_key = draft.idempotency_key
        statement = (
            insert(A2ATask)
            .values(
                id=draft.task_id,
                tenant_id=draft.tenant_id,
                peer_agent_id=draft.peer_agent_id,
                run_id=draft.run_id,
                thread_id=draft.thread_id,
                session_id=draft.session_id,
                context_id=draft.context_id,
                message_id=draft.message_id,
                status="submitted",
                idempotency_key=idempotency_key,
                input_payload={
                    "user_id": draft.user_id,
                    "input_text": draft.input_text,
                    "skill_id": draft.skill_id,
                    "push_destination": draft.push_destination,
                    "metadata": dict(draft.metadata),
                },
            )
            .on_conflict_do_nothing(constraint="uq_a2a_tasks_idempotency")
            .returning(A2ATask.id)
        )
        async with self._session_factory() as session:
            async with session.begin():
                task_id = await session.scalar(statement)
                if task_id is None and idempotency_key is not None:
                    task = await self._get_task_by_idempotency_key(
                        session,
                        tenant_id=draft.tenant_id,
                        idempotency_key=idempotency_key,
                    )
                    if task is None:
                        raise RuntimeError(
                            "A2A task idempotency insert failed without existing row"
                        )
                    record = self._record_from_task(task, event_sequence=1)
                else:
                    event_sequence = await self._append_event(
                        session,
                        task_id=draft.task_id,
                        tenant_id=draft.tenant_id,
                        sequence=1,
                        event_type="task.submitted",
                        payload={
                            "context_id": draft.context_id,
                            "message_id": draft.message_id,
                            "run_id": draft.run_id,
                            "thread_id": draft.thread_id,
                            "session_id": draft.session_id,
                        },
                    )
                    record = A2ATaskRecord(
                        task_id=draft.task_id,
                        tenant_id=draft.tenant_id,
                        run_id=draft.run_id,
                        thread_id=draft.thread_id,
                        session_id=draft.session_id,
                        context_id=draft.context_id,
                        message_id=draft.message_id,
                        status="submitted",
                        event_sequence=event_sequence,
                    )

        if draft.push_destination and self._durable_store is not None:
            outbox_id = await self._durable_store.enqueue_outbox(
                build_a2a_push_outbox_request(
                    record=record,
                    destination=draft.push_destination,
                    draft=draft,
                )
            )
            return A2ATaskRecord(
                task_id=record.task_id,
                tenant_id=record.tenant_id,
                run_id=record.run_id,
                thread_id=record.thread_id,
                session_id=record.session_id,
                context_id=record.context_id,
                message_id=record.message_id,
                status=record.status,
                event_sequence=record.event_sequence,
                outbox_event_id=outbox_id,
            )
        return record

    async def get_task(self, *, tenant_id: str, task_id: str) -> A2ATaskRecord | None:
        async with self._session_factory() as session:
            task = await session.scalar(
                select(A2ATask).where(A2ATask.tenant_id == tenant_id, A2ATask.id == task_id)
            )
            if task is None:
                return None
            latest_sequence = await session.scalar(
                select(A2ATaskEvent.sequence)
                .where(A2ATaskEvent.tenant_id == tenant_id, A2ATaskEvent.task_id == task_id)
                .order_by(A2ATaskEvent.sequence.desc())
                .limit(1)
            )
        return self._record_from_task(task, event_sequence=latest_sequence or 0)

    async def cancel_task(
        self,
        *,
        tenant_id: str,
        task_id: str,
        cancelled_by: str,
        reason: str | None,
    ) -> A2ATaskRecord | None:
        push_draft: A2ATaskDraft | None = None
        async with self._session_factory() as session:
            async with session.begin():
                task = await session.scalar(
                    select(A2ATask)
                    .where(A2ATask.tenant_id == tenant_id, A2ATask.id == task_id)
                    .with_for_update()
                )
                if task is None:
                    return None
                latest_sequence = await session.scalar(
                    select(A2ATaskEvent.sequence)
                    .where(A2ATaskEvent.tenant_id == tenant_id, A2ATaskEvent.task_id == task_id)
                    .order_by(A2ATaskEvent.sequence.desc())
                    .limit(1)
                )
                next_sequence = (latest_sequence or 0) + 1
                task.status = "cancelled"
                await self._append_event(
                    session,
                    task_id=task_id,
                    tenant_id=tenant_id,
                    sequence=next_sequence,
                    event_type="task.cancelled",
                    payload={"cancelled_by": cancelled_by, "reason": reason},
                )
                record = self._record_from_task(task, event_sequence=next_sequence)
                push_draft = self._push_draft_from_task(task)
        if (
            push_draft is not None
            and push_draft.push_destination
            and self._durable_store is not None
        ):
            outbox_id = await self._durable_store.enqueue_outbox(
                build_a2a_push_outbox_request(
                    record=record,
                    destination=push_draft.push_destination,
                    draft=push_draft,
                    event_type="a2a.task.cancelled",
                )
            )
            return A2ATaskRecord(
                task_id=record.task_id,
                tenant_id=record.tenant_id,
                run_id=record.run_id,
                thread_id=record.thread_id,
                session_id=record.session_id,
                context_id=record.context_id,
                message_id=record.message_id,
                status=record.status,
                event_sequence=record.event_sequence,
                outbox_event_id=outbox_id,
            )
        return record

    async def resume_task(
        self,
        *,
        tenant_id: str,
        task_id: str,
        resumed_by: str,
        reason: str | None,
    ) -> A2ATaskRecord | None:
        push_draft: A2ATaskDraft | None = None
        async with self._session_factory() as session:
            async with session.begin():
                task = await session.scalar(
                    select(A2ATask)
                    .where(A2ATask.tenant_id == tenant_id, A2ATask.id == task_id)
                    .with_for_update()
                )
                if task is None:
                    return None
                latest_sequence = await session.scalar(
                    select(A2ATaskEvent.sequence)
                    .where(A2ATaskEvent.tenant_id == tenant_id, A2ATaskEvent.task_id == task_id)
                    .order_by(A2ATaskEvent.sequence.desc())
                    .limit(1)
                )
                next_sequence = (latest_sequence or 0) + 1
                task.status = "submitted"
                await self._append_event(
                    session,
                    task_id=task_id,
                    tenant_id=tenant_id,
                    sequence=next_sequence,
                    event_type="task.resumed",
                    payload={"resumed_by": resumed_by, "reason": reason},
                )
                record = self._record_from_task(task, event_sequence=next_sequence)
                push_draft = self._push_draft_from_task(task)
        if (
            push_draft is not None
            and push_draft.push_destination
            and self._durable_store is not None
        ):
            outbox_id = await self._durable_store.enqueue_outbox(
                build_a2a_push_outbox_request(
                    record=record,
                    destination=push_draft.push_destination,
                    draft=push_draft,
                    event_type="a2a.task.resumed",
                )
            )
            return A2ATaskRecord(
                task_id=record.task_id,
                tenant_id=record.tenant_id,
                run_id=record.run_id,
                thread_id=record.thread_id,
                session_id=record.session_id,
                context_id=record.context_id,
                message_id=record.message_id,
                status=record.status,
                event_sequence=record.event_sequence,
                outbox_event_id=outbox_id,
            )
        return record

    async def list_task_events(
        self,
        *,
        tenant_id: str,
        task_id: str,
    ) -> list[dict[str, object]] | None:
        async with self._session_factory() as session:
            task_exists = await session.scalar(
                select(A2ATask.id).where(A2ATask.tenant_id == tenant_id, A2ATask.id == task_id)
            )
            if task_exists is None:
                return None
            rows = await session.scalars(
                select(A2ATaskEvent)
                .where(A2ATaskEvent.tenant_id == tenant_id, A2ATaskEvent.task_id == task_id)
                .order_by(A2ATaskEvent.sequence.asc())
            )
            events = list(rows)
        return [
            {
                "taskId": event.task_id,
                "tenantId": event.tenant_id,
                "sequence": event.sequence,
                "eventType": event.event_type,
                "payload": event.payload,
                "createdAt": event.created_at,
            }
            for event in events
        ]

    async def save_sdk_task(
        self,
        *,
        tenant_id: str,
        task_id: str,
        context_id: str,
        status: str,
        payload: dict[str, object],
    ) -> None:
        idempotency_key = f"a2a-sdk:{tenant_id}:{task_id}"
        async with self._session_factory() as session:
            async with session.begin():
                task = await session.scalar(
                    select(A2ATask)
                    .where(A2ATask.tenant_id == tenant_id, A2ATask.id == task_id)
                    .with_for_update()
                )
                if task is None:
                    session.add(
                        A2ATask(
                            id=task_id,
                            tenant_id=tenant_id,
                            peer_agent_id=None,
                            run_id=str(payload.get("run_id") or task_id),
                            thread_id=str(payload.get("thread_id") or context_id or task_id),
                            session_id=str(payload.get("session_id") or context_id or task_id),
                            context_id=context_id,
                            message_id=str(payload.get("message_id") or task_id),
                            status=status,
                            idempotency_key=idempotency_key,
                            input_payload={"sdk_task": payload},
                            output_payload=None,
                        )
                    )
                    await self._append_event(
                        session,
                        task_id=task_id,
                        tenant_id=tenant_id,
                        sequence=1,
                        event_type="task.submitted",
                        payload={
                            "source": "a2a_sdk",
                            "context_id": context_id,
                            "status": status,
                        },
                    )
                    return

                previous_status = task.status
                task.status = status
                task.context_id = context_id
                task.input_payload = {"sdk_task": payload}
                if previous_status == status:
                    return
                latest_sequence = await session.scalar(
                    select(A2ATaskEvent.sequence)
                    .where(A2ATaskEvent.tenant_id == tenant_id, A2ATaskEvent.task_id == task_id)
                    .order_by(A2ATaskEvent.sequence.desc())
                    .limit(1)
                )
                await self._append_event(
                    session,
                    task_id=task_id,
                    tenant_id=tenant_id,
                    sequence=(latest_sequence or 0) + 1,
                    event_type="task.status.changed",
                    payload={
                        "source": "a2a_sdk",
                        "context_id": context_id,
                        "previous_status": previous_status,
                        "status": status,
                    },
                )

    async def get_sdk_task(self, *, tenant_id: str, task_id: str) -> dict[str, object] | None:
        async with self._session_factory() as session:
            task = await session.scalar(
                select(A2ATask).where(A2ATask.tenant_id == tenant_id, A2ATask.id == task_id)
            )
        if task is None:
            return None
        payload = cast(Any, task.input_payload.get("sdk_task"))
        return cast(dict[str, object], payload) if isinstance(payload, dict) else None

    async def list_sdk_tasks(
        self,
        *,
        tenant_id: str,
        context_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, object]]:
        statement = select(A2ATask).where(A2ATask.tenant_id == tenant_id)
        if context_id is not None:
            statement = statement.where(A2ATask.context_id == context_id)
        statement = (
            statement.order_by(A2ATask.created_at.desc(), A2ATask.id.desc())
            .limit(limit)
            .offset(offset)
        )
        async with self._session_factory() as session:
            rows = await session.scalars(statement)
            tasks = list(rows)
        payloads: list[dict[str, object]] = []
        for task in tasks:
            payload = cast(Any, task.input_payload.get("sdk_task"))
            if isinstance(payload, dict):
                payloads.append(cast(dict[str, object], payload))
        return payloads

    async def delete_sdk_task(self, *, tenant_id: str, task_id: str) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(
                    delete(A2ATask).where(A2ATask.tenant_id == tenant_id, A2ATask.id == task_id)
                )

    async def _append_event(
        self,
        session: AsyncSession,
        *,
        task_id: str,
        tenant_id: str,
        sequence: int,
        event_type: str,
        payload: dict[str, object],
    ) -> int:
        await session.execute(
            insert(A2ATaskEvent).values(
                id=new_id("a2aevt"),
                task_id=task_id,
                tenant_id=tenant_id,
                sequence=sequence,
                event_type=event_type,
                payload=payload,
            )
        )
        return sequence

    async def _get_task_by_idempotency_key(
        self,
        session: AsyncSession,
        *,
        tenant_id: str,
        idempotency_key: str,
    ) -> A2ATask | None:
        return await session.scalar(
            select(A2ATask).where(
                A2ATask.tenant_id == tenant_id,
                A2ATask.idempotency_key == idempotency_key,
            )
        )

    def _record_from_task(self, task: A2ATask, *, event_sequence: int) -> A2ATaskRecord:
        return A2ATaskRecord(
            task_id=task.id,
            tenant_id=task.tenant_id,
            run_id=task.run_id,
            thread_id=task.thread_id,
            session_id=task.session_id,
            context_id=task.context_id,
            message_id=task.message_id,
            status=task.status,
            event_sequence=event_sequence,
        )

    def _push_draft_from_task(self, task: A2ATask) -> A2ATaskDraft | None:
        payload = task.input_payload
        destination = payload.get("push_destination")
        if not isinstance(destination, str) or not destination.strip():
            return None
        metadata = payload.get("metadata")
        return A2ATaskDraft(
            tenant_id=task.tenant_id,
            peer_agent_id=task.peer_agent_id,
            context_id=task.context_id,
            message_id=task.message_id,
            user_id=str(payload.get("user_id") or "anonymous"),
            input_text=str(payload.get("input_text") or "a2a task lifecycle update"),
            skill_id=cast(str | None, payload.get("skill_id")),
            push_destination=destination,
            metadata=cast(dict[str, Any], metadata) if isinstance(metadata, dict) else {},
            task_id=task.id,
            run_id=task.run_id,
            thread_id=task.thread_id,
            session_id=task.session_id,
            idempotency_key=task.idempotency_key,
        )

    def _peer_record(self, peer: A2APeerAgent) -> A2APeerRecord:
        return A2APeerRecord(
            peer_agent_id=peer.id,
            tenant_id=peer.tenant_id,
            name=peer.name,
            endpoint_url=peer.endpoint_url,
            agent_card=peer.agent_card,
            enabled=peer.enabled,
        )
