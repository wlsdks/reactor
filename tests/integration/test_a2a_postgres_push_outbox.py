from __future__ import annotations

import os
from typing import Any, cast

import pytest
from alembic import command
from alembic.config import Config
from docker.errors import DockerException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from reactor.a2a.peers import A2APeerDraft
from reactor.a2a.tasks import A2ATaskDraft
from reactor.core.settings import get_settings
from reactor.persistence.a2a_store import SqlAlchemyA2ATaskStore
from reactor.persistence.durable_store import SqlAlchemyDurableStore
from reactor.persistence.models import A2ATask, A2ATaskEvent, OutboxEvent

pytestmark = pytest.mark.skipif(
    os.environ.get("REACTOR_TEST_POSTGRES") != "1",
    reason="set REACTOR_TEST_POSTGRES=1 to run Docker-backed A2A push outbox tests",
)


async def test_a2a_task_push_outbox_is_idempotent_against_postgres() -> None:
    try:
        container = cast(Any, postgres_container())
    except DockerException as exc:
        pytest.skip(f"Docker daemon is unavailable for A2A push outbox test: {exc}")
    with container as postgres:
        sync_url = str(postgres.get_connection_url()).replace(
            "postgresql+psycopg2://",
            "postgresql+psycopg://",
        )
        migrate_postgres(sync_url)
        engine = create_async_engine(sync_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        durable_store = SqlAlchemyDurableStore(session_factory)
        a2a_store = SqlAlchemyA2ATaskStore(session_factory, durable_store=durable_store)

        try:
            await a2a_store.register_peer(
                A2APeerDraft(
                    tenant_id="tenant_1",
                    peer_agent_id="peer_1",
                    name="Peer One",
                    endpoint_url="https://peer.example/a2a",
                    agent_card={"name": "Peer One"},
                    enabled=True,
                )
            )
            first = await a2a_store.create_task(
                task_draft(
                    task_id="task_1",
                    run_id="run_1",
                    thread_id="thread_1",
                    session_id="session_1",
                )
            )
            second = await a2a_store.create_task(
                task_draft(
                    task_id="task_duplicate",
                    run_id="run_duplicate",
                    thread_id="thread_duplicate",
                    session_id="session_duplicate",
                )
            )

            async with session_factory() as session:
                tasks = list(await session.scalars(select(A2ATask)))
                events = list(await session.scalars(select(A2ATaskEvent)))
                outbox_events = list(await session.scalars(select(OutboxEvent)))

            assert first.task_id == "task_1"
            assert second.task_id == "task_1"
            assert first.outbox_event_id == second.outbox_event_id
            assert first.outbox_event_id is not None
            assert [(task.id, task.idempotency_key) for task in tasks] == [
                ("task_1", "a2a:tenant_1:ctx_1:msg_1")
            ]
            assert [(event.task_id, event.sequence, event.event_type) for event in events] == [
                ("task_1", 1, "task.submitted")
            ]
            assert [
                (
                    event.destination,
                    event.event_type,
                    event.idempotency_key,
                    event.payload["task_id"],
                    event.payload["peer_agent_id"],
                    event.payload["skill_id"],
                    event.payload["user_id"],
                    event.payload["metadata"],
                )
                for event in outbox_events
            ] == [
                (
                    "https://peer.example/events",
                    "a2a.task.created",
                    "task_1:a2a.task.created:1",
                    "task_1",
                    "peer_1",
                    "research",
                    "user_1",
                    {"priority": "high"},
                )
            ]
        finally:
            await engine.dispose()


async def test_a2a_task_lifecycle_push_outbox_uses_original_destination_against_postgres() -> None:
    try:
        container = cast(Any, postgres_container())
    except DockerException as exc:
        pytest.skip(f"Docker daemon is unavailable for A2A lifecycle push outbox test: {exc}")
    with container as postgres:
        sync_url = str(postgres.get_connection_url()).replace(
            "postgresql+psycopg2://",
            "postgresql+psycopg://",
        )
        migrate_postgres(sync_url)
        engine = create_async_engine(sync_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        durable_store = SqlAlchemyDurableStore(session_factory)
        a2a_store = SqlAlchemyA2ATaskStore(session_factory, durable_store=durable_store)

        try:
            await a2a_store.register_peer(
                A2APeerDraft(
                    tenant_id="tenant_1",
                    peer_agent_id="peer_1",
                    name="Peer One",
                    endpoint_url="https://peer.example/a2a",
                    agent_card={"name": "Peer One"},
                    enabled=True,
                )
            )
            created = await a2a_store.create_task(
                task_draft(
                    task_id="task_1",
                    run_id="run_1",
                    thread_id="thread_1",
                    session_id="session_1",
                )
            )
            cancelled = await a2a_store.cancel_task(
                tenant_id="tenant_1",
                task_id=created.task_id,
                cancelled_by="admin_1",
                reason="operator requested",
            )
            resumed = await a2a_store.resume_task(
                tenant_id="tenant_1",
                task_id=created.task_id,
                resumed_by="admin_1",
                reason="operator resumed",
            )

            async with session_factory() as session:
                outbox_events = list(
                    await session.scalars(
                        select(OutboxEvent).order_by(OutboxEvent.created_at.asc())
                    )
                )

            assert cancelled is not None
            assert resumed is not None
            assert [
                (
                    event.destination,
                    event.event_type,
                    event.idempotency_key,
                    event.payload["status"],
                    event.payload["event_sequence"],
                    event.payload["peer_agent_id"],
                    event.payload["skill_id"],
                    event.payload["user_id"],
                    event.payload["metadata"],
                )
                for event in outbox_events
            ] == [
                (
                    "https://peer.example/events",
                    "a2a.task.created",
                    "task_1:a2a.task.created:1",
                    "submitted",
                    1,
                    "peer_1",
                    "research",
                    "user_1",
                    {"priority": "high"},
                ),
                (
                    "https://peer.example/events",
                    "a2a.task.cancelled",
                    "task_1:a2a.task.cancelled:2",
                    "cancelled",
                    2,
                    "peer_1",
                    "research",
                    "user_1",
                    {"priority": "high"},
                ),
                (
                    "https://peer.example/events",
                    "a2a.task.resumed",
                    "task_1:a2a.task.resumed:3",
                    "submitted",
                    3,
                    "peer_1",
                    "research",
                    "user_1",
                    {"priority": "high"},
                ),
            ]
        finally:
            await engine.dispose()


async def test_a2a_sdk_task_persistence_records_status_timeline_against_postgres() -> None:
    try:
        container = cast(Any, postgres_container())
    except DockerException as exc:
        pytest.skip(f"Docker daemon is unavailable for A2A SDK task persistence test: {exc}")
    with container as postgres:
        sync_url = str(postgres.get_connection_url()).replace(
            "postgresql+psycopg2://",
            "postgresql+psycopg://",
        )
        migrate_postgres(sync_url)
        engine = create_async_engine(sync_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        a2a_store = SqlAlchemyA2ATaskStore(session_factory)

        try:
            await a2a_store.save_sdk_task(
                tenant_id="tenant_1",
                task_id="sdk_task_1",
                context_id="ctx_1",
                status="submitted",
                payload={"id": "sdk_task_1", "context_id": "ctx_1"},
            )
            await a2a_store.save_sdk_task(
                tenant_id="tenant_1",
                task_id="sdk_task_1",
                context_id="ctx_1",
                status="working",
                payload={"id": "sdk_task_1", "context_id": "ctx_1", "status": "working"},
            )

            async with session_factory() as session:
                task = await session.scalar(
                    select(A2ATask).where(
                        A2ATask.tenant_id == "tenant_1",
                        A2ATask.id == "sdk_task_1",
                    )
                )
                events = list(
                    await session.scalars(
                        select(A2ATaskEvent)
                        .where(
                            A2ATaskEvent.tenant_id == "tenant_1",
                            A2ATaskEvent.task_id == "sdk_task_1",
                        )
                        .order_by(A2ATaskEvent.sequence.asc())
                    )
                )

            assert task is not None
            assert task.status == "working"
            assert [(event.sequence, event.event_type, event.payload) for event in events] == [
                (
                    1,
                    "task.submitted",
                    {"source": "a2a_sdk", "context_id": "ctx_1", "status": "submitted"},
                ),
                (
                    2,
                    "task.status.changed",
                    {
                        "source": "a2a_sdk",
                        "context_id": "ctx_1",
                        "previous_status": "submitted",
                        "status": "working",
                    },
                ),
            ]
        finally:
            await engine.dispose()


def task_draft(
    *,
    task_id: str,
    run_id: str,
    thread_id: str,
    session_id: str,
) -> A2ATaskDraft:
    return A2ATaskDraft(
        tenant_id="tenant_1",
        peer_agent_id="peer_1",
        context_id="ctx_1",
        message_id="msg_1",
        user_id="user_1",
        input_text="delegate this",
        skill_id="research",
        push_destination="https://peer.example/events",
        metadata={"priority": "high"},
        task_id=task_id,
        run_id=run_id,
        thread_id=thread_id,
        session_id=session_id,
        idempotency_key="a2a:tenant_1:ctx_1:msg_1",
    )


def postgres_container() -> PostgresContainer:
    return PostgresContainer(
        image="pgvector/pgvector:0.8.3-pg18-trixie",
        username="reactor",
        password="reactor",  # noqa: S106 - ephemeral Docker test credential
        dbname="reactor",
    )


def migrate_postgres(sync_url: str) -> None:
    previous_url = os.environ.get("REACTOR_DATABASE_URL")
    os.environ["REACTOR_DATABASE_URL"] = sync_url
    get_settings.cache_clear()
    try:
        command.upgrade(Config("alembic.ini"), "head")
    finally:
        if previous_url is None:
            os.environ.pop("REACTOR_DATABASE_URL", None)
        else:
            os.environ["REACTOR_DATABASE_URL"] = previous_url
        get_settings.cache_clear()
