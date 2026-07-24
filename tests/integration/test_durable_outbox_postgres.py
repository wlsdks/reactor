from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from reactor.core.settings import get_settings
from reactor.persistence.durable_store import OutboxRequest, SqlAlchemyDurableStore
from reactor.persistence.models import OutboxEvent

pytestmark = pytest.mark.skipif(
    os.environ.get("REACTOR_TEST_POSTGRES") != "1",
    reason="set REACTOR_TEST_POSTGRES=1 to run Docker-backed durable outbox tests",
)


async def test_durable_outbox_reclaims_expired_dispatching_lease() -> None:
    try:
        container = cast(Any, postgres_container())
    except Exception as exc:  # pragma: no cover - depends on local Docker availability
        pytest.skip(f"Docker daemon is unavailable for durable outbox test: {exc}")

    with container as postgres:
        sync_url = str(postgres.get_connection_url()).replace(
            "postgresql+psycopg2://",
            "postgresql+psycopg://",
        )
        migrate_postgres(sync_url)
        engine = create_async_engine(sync_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        store = SqlAlchemyDurableStore(session_factory)
        try:
            event_id = await store.enqueue_outbox(
                OutboxRequest(
                    tenant_id="tenant_1",
                    destination="slack.events",
                    event_type="slack.event_callback",
                    idempotency_key="slack:event:tenant_1:EvLease",
                    payload={"entrypoint": "events_api"},
                )
            )

            first_claim = await store.claim_outbox(
                tenant_id="tenant_1",
                lease_owner="worker_1",
                limit=1,
            )

            assert [lease.event_id for lease in first_claim] == [event_id]
            async with session_factory() as session:
                row = await session.get(OutboxEvent, event_id)
                assert row is not None
                assert row.status == "dispatching"
                assert row.lease_owner == "worker_1"
                assert row.lease_expires_at is not None
                assert row.attempt == 1

            await store.mark_outbox_dispatched(event_id=event_id, lease_owner="worker_1")
            async with session_factory() as session:
                dispatched = await session.get(OutboxEvent, event_id)
                assert dispatched is not None
                assert dispatched.status == "dispatched"
                assert dispatched.lease_owner is None
                assert dispatched.lease_expires_at is None

            reclaim_id = await store.enqueue_outbox(
                OutboxRequest(
                    tenant_id="tenant_1",
                    destination="slack.events",
                    event_type="slack.event_callback",
                    idempotency_key="slack:event:tenant_1:EvReclaim",
                    payload={"entrypoint": "events_api"},
                )
            )
            await store.claim_outbox(tenant_id="tenant_1", lease_owner="worker_1", limit=1)
            async with session_factory() as session:
                async with session.begin():
                    await session.execute(
                        update(OutboxEvent)
                        .where(OutboxEvent.id == reclaim_id)
                        .values(lease_expires_at=datetime.now(UTC) - timedelta(seconds=1))
                    )

            reclaimed = await store.claim_outbox(
                tenant_id="tenant_1",
                lease_owner="worker_2",
                limit=1,
            )

            assert [lease.event_id for lease in reclaimed] == [reclaim_id]
            assert reclaimed[0].attempt == 2
            async with session_factory() as session:
                row = await session.scalar(select(OutboxEvent).where(OutboxEvent.id == reclaim_id))
                assert row is not None
                assert row.status == "dispatching"
                assert row.lease_owner == "worker_2"
                assert row.attempt == 2

            await store.mark_outbox_dispatched(event_id=reclaim_id, lease_owner="worker_1")
            async with session_factory() as session:
                row = await session.scalar(select(OutboxEvent).where(OutboxEvent.id == reclaim_id))
                assert row is not None
                assert row.status == "dispatching"
                assert row.lease_owner == "worker_2"

            await store.mark_outbox_dispatched(event_id=reclaim_id, lease_owner="worker_2")
            async with session_factory() as session:
                row = await session.scalar(select(OutboxEvent).where(OutboxEvent.id == reclaim_id))
                assert row is not None
                assert row.status == "dispatched"
                assert row.lease_owner is None
                assert row.lease_expires_at is None
        finally:
            await engine.dispose()


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
