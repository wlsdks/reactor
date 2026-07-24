from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from alembic import command
from alembic.config import Config
from docker.errors import DockerException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from reactor.core.settings import get_settings
from reactor.memory.policy import MemoryNamespaceKey
from reactor.memory.service import (
    MemoryProposalDraft,
    MemoryProposalService,
)
from reactor.persistence.memory_store import SqlAlchemyMemoryStore
from reactor.persistence.models import MemoryEmbedding, MemoryItem, MemoryProposal

pytestmark = pytest.mark.skipif(
    os.environ.get("REACTOR_TEST_POSTGRES") != "1",
    reason="set REACTOR_TEST_POSTGRES=1 to run Docker-backed Postgres lifecycle tests",
)


async def test_memory_lifecycle_executes_against_postgres_tables() -> None:
    try:
        container = cast(Any, postgres_container())
    except DockerException as exc:
        pytest.skip(f"Docker daemon is unavailable for Postgres memory lifecycle test: {exc}")
    with container as postgres:
        sync_url = str(postgres.get_connection_url()).replace(
            "postgresql+psycopg2://",
            "postgresql+psycopg://",
        )
        migrate_postgres(sync_url)
        engine = create_async_engine(sync_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        store = SqlAlchemyMemoryStore(session_factory)
        service = MemoryProposalService(id_factory=IdSequence(), clock=fixed_clock)

        try:
            proposal = service.propose(
                MemoryProposalDraft(
                    namespace=memory_namespace(),
                    content="User prefers concise Korean status updates.",
                    source_payload={"run_id": "run_1", "message_range": [1, 2]},
                    extraction_model="langmem",
                    extraction_prompt_version="memory-v1",
                    confidence=0.87,
                )
            )
            await store.save_proposal(proposal)
            promotion = service.promote(
                proposal,
                reviewer_id="reviewer_1",
                reason="stable user preference",
            )
            await store.save_promotion(promotion)
            active_items = await store.list_active_items(memory_namespace(), limit=5)
            await insert_embedding(session_factory, memory_id=promotion.item.id)
            tombstone = service.tombstone(
                promotion.item,
                actor_id="user_1",
                reason="user requested deletion",
            )
            await store.save_tombstone(tombstone)

            async with session_factory() as session:
                proposals = list(await session.scalars(select(MemoryProposal)))
                items = list(await session.scalars(select(MemoryItem)))
                embeddings = list(await session.scalars(select(MemoryEmbedding)))

            assert [item.content for item in active_items] == [
                "User prefers concise Korean status updates."
            ]
            assert active_items[0].metadata["proposal_id"] == proposal.id
            assert len(proposals) == 1
            assert proposals[0].status == "approved"
            assert proposals[0].decision_reason == "stable user preference"
            assert len(items) == 1
            assert items[0].status == "tombstoned"
            assert items[0].item_metadata["tombstone_actor_id"] == "user_1"
            assert embeddings == []
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


async def insert_embedding(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    memory_id: str,
) -> None:
    async with session_factory() as session:
        async with session.begin():
            session.add(
                MemoryEmbedding(
                    memory_id=memory_id,
                    tenant_id="tenant_1",
                    embedding=[0.0] * 1536,
                    embedding_model="text-embedding-3-small",
                )
            )


def memory_namespace() -> MemoryNamespaceKey:
    return MemoryNamespaceKey(
        tenant_id="tenant_1",
        subject_type="user",
        subject_id="user_1",
        memory_type="semantic",
        visibility="user",
    )


def fixed_clock() -> datetime:
    return datetime(2026, 6, 26, tzinfo=UTC)


class IdSequence:
    def __init__(self) -> None:
        self._next = 1

    def __call__(self) -> str:
        value = f"id_{self._next}"
        self._next += 1
        return value
