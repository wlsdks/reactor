from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from alembic import command
from alembic.config import Config
from docker.errors import DockerException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from reactor.core.settings import get_settings
from reactor.persistence.rag_ingest_store import (
    RagChunkMigrationRecord,
    RagDocumentMigrationRecord,
    RagSourceMigrationRecord,
    SqlAlchemyFaqDocumentSink,
)
from reactor.persistence.repositories.rag_postgres import PostgresRagRetriever
from reactor.rag.retriever import RetrievalQuery

pytestmark = pytest.mark.skipif(
    os.environ.get("REACTOR_TEST_POSTGRES") != "1",
    reason="set REACTOR_TEST_POSTGRES=1 to run Docker-backed Postgres RAG lifecycle tests",
)


async def test_rag_lifecycle_executes_pgvector_and_full_text_retrieval_against_postgres() -> None:
    try:
        container = cast(Any, postgres_container())
    except DockerException as exc:
        pytest.skip(f"Docker daemon is unavailable for Postgres RAG lifecycle test: {exc}")
    with container as postgres:
        sync_url = str(postgres.get_connection_url()).replace(
            "postgresql+psycopg2://",
            "postgresql+psycopg://",
        )
        migrate_postgres(sync_url)
        engine = create_async_engine(sync_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        sink = SqlAlchemyFaqDocumentSink(session_factory)
        retriever = PostgresRagRetriever(cast(Any, session_factory))

        try:
            await save_rag_fixture(sink)

            ranked = await retriever.retrieve(
                RetrievalQuery(
                    tenant_id="tenant_1",
                    collection="docs",
                    query="LangGraph RAG",
                    principal_id="user_1",
                    groups=(),
                    limit=5,
                ),
                query_embedding(),
            )
            stats = await sink.stats_by_collection(tenant_id="tenant_1")

            assert [item.chunk.document_id for item in ranked] == ["doc_tenant"]
            assert ranked[0].vector_rank == 1
            assert ranked[0].keyword_rank == 1
            assert ranked[0].chunk.metadata["source_uri"] == "https://docs.example/reactor"
            assert [
                (item.collection, item.chunk_count, item.embedded_chunk_count) for item in stats
            ] == [("docs", 2, 2)]
        finally:
            await engine.dispose()


async def test_rag_lifecycle_filters_private_documents_by_authenticated_groups() -> None:
    try:
        container = cast(Any, postgres_container())
    except DockerException as exc:
        pytest.skip(f"Docker daemon is unavailable for Postgres RAG ACL lifecycle test: {exc}")
    with container as postgres:
        sync_url = str(postgres.get_connection_url()).replace(
            "postgresql+psycopg2://",
            "postgresql+psycopg://",
        )
        migrate_postgres(sync_url)
        engine = create_async_engine(sync_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        sink = SqlAlchemyFaqDocumentSink(session_factory)
        retriever = PostgresRagRetriever(cast(Any, session_factory))

        try:
            await save_rag_fixture(sink, include_group_private=True)

            employee_ranked = await retriever.retrieve(
                RetrievalQuery(
                    tenant_id="tenant_1",
                    collection="docs",
                    query="executive salary",
                    principal_id="employee_1",
                    groups=("engineering",),
                    limit=5,
                ),
                query_embedding(),
            )
            executive_ranked = await retriever.retrieve(
                RetrievalQuery(
                    tenant_id="tenant_1",
                    collection="docs",
                    query="executive salary",
                    principal_id="executive_1",
                    groups=("executive",),
                    limit=5,
                ),
                query_embedding(),
            )

            assert [item.chunk.document_id for item in employee_ranked] == ["doc_tenant"]
            assert {item.chunk.document_id for item in executive_ranked} == {
                "doc_tenant",
                "doc_private_group",
            }
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


async def save_rag_fixture(
    sink: SqlAlchemyFaqDocumentSink,
    *,
    include_group_private: bool = False,
) -> None:
    created_at = datetime(2026, 6, 26, tzinfo=UTC)
    await sink.save_source(
        RagSourceMigrationRecord(
            id="source_tenant",
            tenant_id="tenant_1",
            collection="docs",
            source_uri="https://docs.example/reactor",
            source_type="docs",
            checksum="checksum_tenant",
            metadata={"kind": "manual"},
            created_at=created_at,
        )
    )
    await sink.save_document(
        RagDocumentMigrationRecord(
            id="doc_tenant",
            tenant_id="tenant_1",
            source_id="source_tenant",
            collection="docs",
            title="Reactor RAG",
            version="v1",
            acl={"visibility": "tenant"},
            metadata={"section": "runtime"},
            created_at=created_at,
        )
    )
    await sink.save_chunk(
        RagChunkMigrationRecord(
            id="chunk_tenant",
            tenant_id="tenant_1",
            document_id="doc_tenant",
            collection="docs",
            chunk_index=0,
            content="LangGraph orchestrates Reactor RAG with pgvector hybrid retrieval.",
            content_hash="hash_tenant",
            embedding=query_embedding(),
            metadata={"section": "runtime"},
            created_at=created_at,
        )
    )
    await sink.save_source(
        RagSourceMigrationRecord(
            id="source_private",
            tenant_id="tenant_1",
            collection="docs",
            source_uri="https://docs.example/private",
            source_type="docs",
            checksum="checksum_private",
            metadata={"kind": "manual"},
            created_at=created_at,
        )
    )
    await sink.save_document(
        RagDocumentMigrationRecord(
            id="doc_private",
            tenant_id="tenant_1",
            source_id="source_private",
            collection="docs",
            title="Private Reactor RAG",
            version="v1",
            acl={"visibility": "private", "users": ["user_2"]},
            metadata={"section": "runtime"},
            created_at=created_at,
        )
    )
    await sink.save_chunk(
        RagChunkMigrationRecord(
            id="chunk_private",
            tenant_id="tenant_1",
            document_id="doc_private",
            collection="docs",
            chunk_index=0,
            content="LangGraph RAG private note that user_1 must not retrieve.",
            content_hash="hash_private",
            embedding=query_embedding(),
            metadata={"section": "private"},
            created_at=created_at,
        )
    )
    if not include_group_private:
        return
    await sink.save_source(
        RagSourceMigrationRecord(
            id="source_private_group",
            tenant_id="tenant_1",
            collection="docs",
            source_uri="https://docs.example/executive-salary",
            source_type="docs",
            checksum="checksum_private_group",
            metadata={"kind": "manual"},
            created_at=created_at,
        )
    )
    await sink.save_document(
        RagDocumentMigrationRecord(
            id="doc_private_group",
            tenant_id="tenant_1",
            source_id="source_private_group",
            collection="docs",
            title="Executive Salary",
            version="v1",
            acl={"visibility": "private", "groups": ["executive"]},
            metadata={"section": "compensation"},
            created_at=created_at,
        )
    )
    await sink.save_chunk(
        RagChunkMigrationRecord(
            id="chunk_private_group",
            tenant_id="tenant_1",
            document_id="doc_private_group",
            collection="docs",
            chunk_index=0,
            content="Executive salary private note that only executive group can retrieve.",
            content_hash="hash_private_group",
            embedding=query_embedding(),
            metadata={"section": "compensation"},
            created_at=created_at,
        )
    )


def query_embedding() -> list[float]:
    return [1.0] + [0.0] * 1535
