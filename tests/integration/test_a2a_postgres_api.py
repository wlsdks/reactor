from __future__ import annotations

import os
from typing import Any, cast

import pytest
from alembic import command
from alembic.config import Config
from docker.errors import DockerException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from reactor.api.app import create_app
from reactor.core.settings import Settings, get_settings
from reactor.persistence.a2a_store import SqlAlchemyA2ATaskStore
from reactor.persistence.durable_store import SqlAlchemyDurableStore
from reactor.persistence.models import A2APeerAgent, A2ATask, A2ATaskEvent, OutboxEvent

pytestmark = pytest.mark.skipif(
    os.environ.get("REACTOR_TEST_POSTGRES") != "1",
    reason="set REACTOR_TEST_POSTGRES=1 to run Docker-backed A2A API tests",
)

ADMIN_HEADERS = {
    "X-Reactor-Admin": "true",
    "X-Reactor-User-Id": "admin_1",
    "X-Reactor-Tenant-Id": "tenant_1",
}


async def test_a2a_rest_api_persists_peers_tasks_and_push_outbox_against_postgres() -> None:
    try:
        container = cast(Any, postgres_container())
    except DockerException as exc:
        pytest.skip(f"Docker daemon is unavailable for A2A API test: {exc}")
    with container as postgres:
        sync_url = str(postgres.get_connection_url()).replace(
            "postgresql+psycopg2://",
            "postgresql+psycopg://",
        )
        migrate_postgres(sync_url)
        engine = create_async_engine(sync_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        store = SqlAlchemyA2ATaskStore(
            session_factory,
            durable_store=SqlAlchemyDurableStore(session_factory),
        )
        app = create_app()
        app.state.reactor = A2AApiContainer(store)
        transport = ASGITransport(app=app)

        try:
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                registered = await client.post(
                    "/v1/a2a/agents",
                    headers=ADMIN_HEADERS,
                    json={
                        "tenantId": "tenant_1",
                        "name": "sample-peer",
                        "endpointUrl": "https://peer.example/a2a",
                        "agentCard": {
                            "name": "Sample Peer",
                            "protocolVersion": "1.0",
                        },
                    },
                )
                peer_id = registered.json()["peerAgentId"]
                listed = await client.get(
                    "/v1/a2a/agents",
                    params={"tenant_id": "tenant_1"},
                    headers=ADMIN_HEADERS,
                )
                created = await client.post(
                    "/v1/a2a/tasks",
                    headers=ADMIN_HEADERS,
                    json={
                        "tenantId": "tenant_1",
                        "peerAgentId": peer_id,
                        "contextId": "ctx_1",
                        "messageId": "msg_1",
                        "userId": "user_1",
                        "inputText": "delegate this safely",
                        "skillId": "plan",
                        "pushDestination": "https://peer.example/events",
                        "metadata": {"source": "api-test"},
                    },
                )
                duplicate = await client.post(
                    "/v1/a2a/tasks",
                    headers=ADMIN_HEADERS,
                    json={
                        "tenantId": "tenant_1",
                        "peerAgentId": peer_id,
                        "contextId": "ctx_1",
                        "messageId": "msg_1",
                        "userId": "user_1",
                        "inputText": "delegate this safely",
                        "skillId": "plan",
                        "pushDestination": "https://peer.example/events",
                    },
                )
                fetched = await client.get(
                    f"/v1/a2a/tasks/{created.json()['taskId']}",
                    params={"tenant_id": "tenant_1"},
                    headers=ADMIN_HEADERS,
                )
                timeline = await client.get(
                    f"/v1/a2a/tasks/{created.json()['taskId']}/events",
                    params={"tenant_id": "tenant_1"},
                    headers=ADMIN_HEADERS,
                )
                cancelled = await client.post(
                    f"/v1/a2a/tasks/{created.json()['taskId']}/cancel",
                    headers=ADMIN_HEADERS,
                    json={"reason": "operator requested"},
                )
                cancelled_timeline = await client.get(
                    f"/v1/a2a/tasks/{created.json()['taskId']}/events",
                    params={"tenant_id": "tenant_1"},
                    headers=ADMIN_HEADERS,
                )
                resumed = await client.post(
                    f"/v1/a2a/tasks/{created.json()['taskId']}/resume",
                    headers=ADMIN_HEADERS,
                    json={"reason": "operator resumed"},
                )
                resumed_timeline = await client.get(
                    f"/v1/a2a/tasks/{created.json()['taskId']}/events",
                    params={"tenant_id": "tenant_1"},
                    headers=ADMIN_HEADERS,
                )
                cross_tenant_timeline = await client.get(
                    f"/v1/a2a/tasks/{created.json()['taskId']}/events",
                    params={"tenant_id": "tenant_2"},
                    headers={**ADMIN_HEADERS, "X-Reactor-Tenant-Id": "tenant_2"},
                )
                missing = await client.get(
                    "/v1/a2a/tasks/missing",
                    params={"tenant_id": "tenant_1"},
                    headers=ADMIN_HEADERS,
                )
                missing_policy = await client.get(
                    "/v1/a2a/access-policy",
                    params={"tenant_id": "tenant_1"},
                    headers=ADMIN_HEADERS,
                )
                saved_policy = await client.put(
                    "/v1/a2a/access-policy",
                    headers=ADMIN_HEADERS,
                    json={
                        "tenantId": "tenant_1",
                        "allowInbound": True,
                        "allowOutbound": True,
                        "allowedSkills": ["plan"],
                    },
                )
                fetched_policy = await client.get(
                    "/v1/a2a/access-policy",
                    params={"tenant_id": "tenant_1"},
                    headers=ADMIN_HEADERS,
                )
                denied_skill = await client.post(
                    "/v1/a2a/tasks",
                    headers=ADMIN_HEADERS,
                    json={
                        "tenantId": "tenant_1",
                        "peerAgentId": peer_id,
                        "contextId": "ctx_2",
                        "messageId": "msg_2",
                        "userId": "user_1",
                        "inputText": "delegate disallowed skill",
                        "skillId": "write",
                    },
                )
                allowed_skill = await client.post(
                    "/v1/a2a/tasks",
                    headers=ADMIN_HEADERS,
                    json={
                        "tenantId": "tenant_1",
                        "peerAgentId": peer_id,
                        "contextId": "ctx_3",
                        "messageId": "msg_3",
                        "userId": "user_1",
                        "inputText": "delegate allowed skill",
                        "skillId": "plan",
                    },
                )

            async with session_factory() as session:
                peers = list(await session.scalars(select(A2APeerAgent)))
                tasks = list(await session.scalars(select(A2ATask)))
                events = list(await session.scalars(select(A2ATaskEvent)))
                outbox_events = list(await session.scalars(select(OutboxEvent)))

            assert registered.status_code == 200
            assert registered.json()["name"] == "sample-peer"
            assert listed.status_code == 200
            assert listed.json()["agents"][0]["peerAgentId"] == peer_id
            assert created.status_code == 200
            assert created.json()["tenantId"] == "tenant_1"
            assert created.json()["status"] == "submitted"
            assert created.json()["eventSequence"] == 1
            assert created.json()["outboxEventId"] is not None
            assert duplicate.status_code == 200
            assert duplicate.json()["taskId"] == created.json()["taskId"]
            assert duplicate.json()["outboxEventId"] == created.json()["outboxEventId"]
            assert fetched.status_code == 200
            assert fetched.json()["taskId"] == created.json()["taskId"]
            assert timeline.status_code == 200
            assert [
                (
                    event["taskId"],
                    event["tenantId"],
                    event["sequence"],
                    event["eventType"],
                    event["payload"]["context_id"],
                    event["payload"]["message_id"],
                )
                for event in timeline.json()["events"]
            ] == [
                (
                    created.json()["taskId"],
                    "tenant_1",
                    1,
                    "task.submitted",
                    "ctx_1",
                    "msg_1",
                )
            ]
            assert cancelled.status_code == 200
            assert cancelled.json()["status"] == "cancelled"
            assert cancelled.json()["eventSequence"] == 2
            assert [
                (event["sequence"], event["eventType"], event["payload"])
                for event in cancelled_timeline.json()["events"]
            ] == [
                (
                    1,
                    "task.submitted",
                    {
                        "context_id": "ctx_1",
                        "message_id": "msg_1",
                        "run_id": created.json()["runId"],
                        "session_id": created.json()["sessionId"],
                        "thread_id": created.json()["threadId"],
                    },
                ),
                (
                    2,
                    "task.cancelled",
                    {"cancelled_by": "admin_1", "reason": "operator requested"},
                ),
            ]
            assert resumed.status_code == 200
            assert resumed.json()["status"] == "submitted"
            assert resumed.json()["eventSequence"] == 3
            assert [
                (event["sequence"], event["eventType"], event["payload"])
                for event in resumed_timeline.json()["events"]
            ][-2:] == [
                (
                    2,
                    "task.cancelled",
                    {"cancelled_by": "admin_1", "reason": "operator requested"},
                ),
                (
                    3,
                    "task.resumed",
                    {"resumed_by": "admin_1", "reason": "operator resumed"},
                ),
            ]
            assert cross_tenant_timeline.status_code == 404
            assert missing.status_code == 404
            assert missing.json()["detail"] == "A2A task not found"
            assert missing_policy.status_code == 404
            assert missing_policy.json()["detail"] == "A2A access policy not found"
            assert saved_policy.status_code == 200
            assert saved_policy.json()["allowedSkills"] == ["plan"]
            assert saved_policy.json()["allowOutbound"] is True
            assert fetched_policy.status_code == 200
            assert fetched_policy.json() == saved_policy.json()
            assert denied_skill.status_code == 403
            assert denied_skill.json()["detail"] == "A2A skill is not allowed"
            assert allowed_skill.status_code == 200
            assert allowed_skill.json()["status"] == "submitted"
            assert [(peer.tenant_id, peer.name, peer.endpoint_url) for peer in peers] == [
                ("tenant_1", "sample-peer", "https://peer.example/a2a")
            ]
            assert [
                (task.id, task.peer_agent_id, task.idempotency_key, task.status) for task in tasks
            ] == [
                (
                    created.json()["taskId"],
                    peer_id,
                    "a2a:tenant_1:ctx_1:msg_1",
                    "submitted",
                ),
                (
                    allowed_skill.json()["taskId"],
                    peer_id,
                    "a2a:tenant_1:ctx_3:msg_3",
                    "submitted",
                ),
            ]
            assert [(event.task_id, event.sequence, event.event_type) for event in events] == [
                (created.json()["taskId"], 1, "task.submitted"),
                (created.json()["taskId"], 2, "task.cancelled"),
                (created.json()["taskId"], 3, "task.resumed"),
                (allowed_skill.json()["taskId"], 1, "task.submitted"),
            ]
            assert "a2a:tenant_1:ctx_2:msg_2" not in {task.idempotency_key for task in tasks}
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
                    f"{created.json()['taskId']}:a2a.task.created:1",
                    created.json()["taskId"],
                    peer_id,
                    "plan",
                    "user_1",
                    {"source": "api-test"},
                ),
                (
                    "https://peer.example/events",
                    "a2a.task.cancelled",
                    f"{created.json()['taskId']}:a2a.task.cancelled:2",
                    created.json()["taskId"],
                    peer_id,
                    "plan",
                    "user_1",
                    {"source": "api-test"},
                ),
                (
                    "https://peer.example/events",
                    "a2a.task.resumed",
                    f"{created.json()['taskId']}:a2a.task.resumed:3",
                    created.json()["taskId"],
                    peer_id,
                    "plan",
                    "user_1",
                    {"source": "api-test"},
                ),
            ]
        finally:
            await engine.dispose()


class A2AApiContainer:
    def __init__(self, store: SqlAlchemyA2ATaskStore) -> None:
        self.settings = Settings()
        self._store = store

    def a2a_task_store(self) -> SqlAlchemyA2ATaskStore:
        return self._store


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
