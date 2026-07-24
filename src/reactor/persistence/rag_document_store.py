from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

from sqlalchemy import delete, func, literal, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql import cast as sql_cast

from reactor.persistence.models import RagChunk, RagDocument
from reactor.persistence.rag_ingest_store import (
    RagChunkMigrationRecord,
    RagDocumentMigrationRecord,
    RagSourceMigrationRecord,
)
from reactor.persistence.repositories.rag_postgres import (
    acl_predicate,
    set_rag_rls_context_values,
)
from reactor.rag.document_management import DocumentSearchResult, ManagedDocument
from reactor.rag.retriever import RetrievalQuery


class SqlAlchemyRagDocumentStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list_documents(
        self,
        *,
        tenant_id: str,
        collection: str,
        limit: int,
        principal_id: str,
        groups: tuple[str, ...],
    ) -> list[DocumentSearchResult]:
        query = RetrievalQuery(
            tenant_id=tenant_id,
            collection=collection,
            query="list documents",
            principal_id=principal_id,
            groups=groups,
            limit=limit,
        )
        query.validate()
        acl = sql_cast(RagDocument.acl, JSONB)
        statement = (
            select(
                RagChunk.id,
                RagChunk.content,
                RagChunk.chunk_metadata,
                RagChunk.created_at,
            )
            .join(RagDocument, RagDocument.id == RagChunk.document_id)
            .where(RagChunk.tenant_id == tenant_id, RagChunk.collection == collection)
            .where(
                RagDocument.tenant_id == tenant_id,
                RagDocument.collection == collection,
                acl_predicate(acl, query),
            )
            .order_by(RagChunk.created_at.desc(), RagChunk.id.asc())
            .limit(limit)
        )
        async with self._session_factory() as session:
            await set_rag_rls_context_values(
                session,
                tenant_id=tenant_id,
                user_id=principal_id,
                groups=groups,
            )
            rows = await session.execute(statement)
            return [
                DocumentSearchResult(
                    id=str(row.id),
                    content=str(row.content),
                    metadata=metadata_dict(row.chunk_metadata),
                    score=None,
                )
                for row in rows.all()
            ]

    async def find_duplicate_content(
        self,
        *,
        tenant_id: str,
        collection: str,
        content_hash: str,
    ) -> str | None:
        statement = (
            select(RagChunk.id)
            .where(
                RagChunk.tenant_id == tenant_id,
                RagChunk.collection == collection,
                RagChunk.content_hash == content_hash,
            )
            .order_by(RagChunk.created_at.desc(), RagChunk.id.asc())
            .limit(1)
        )
        async with self._session_factory() as session:
            await set_rag_rls_context_values(
                session, tenant_id=tenant_id, user_id="rag_document_store"
            )
            row_id = await session.scalar(statement)
        return str(row_id) if row_id is not None else None

    async def save_document(
        self,
        *,
        source: RagSourceMigrationRecord,
        document: RagDocumentMigrationRecord,
        chunks: Sequence[RagChunkMigrationRecord],
    ) -> ManagedDocument:
        async with self._session_factory() as session:
            async with session.begin():
                await set_rag_rls_context_values(
                    session, tenant_id=document.tenant_id, user_id="rag_document_store"
                )
                from reactor.persistence.rag_ingest_store import (
                    build_rag_chunk_migration_upsert,
                    build_rag_document_migration_upsert,
                    build_rag_source_migration_upsert,
                )

                await session.execute(build_rag_source_migration_upsert(source))
                await session.execute(build_rag_document_migration_upsert(document))
                for chunk in chunks:
                    await session.execute(build_rag_chunk_migration_upsert(chunk))
        return ManagedDocument(
            document_id=document.id,
            content="\n".join(chunk.content for chunk in chunks),
            metadata=dict(document.metadata),
            chunk_ids=[chunk.id for chunk in chunks],
        )

    async def search_documents(
        self,
        *,
        tenant_id: str,
        collection: str,
        query: str,
        limit: int,
        similarity_threshold: float,
        principal_id: str,
        groups: tuple[str, ...],
    ) -> list[DocumentSearchResult]:
        retrieval_query = RetrievalQuery(
            tenant_id=tenant_id,
            collection=collection,
            query=query,
            principal_id=principal_id,
            groups=groups,
            limit=limit,
        )
        retrieval_query.validate()
        config = literal("simple").cast(postgresql.REGCONFIG)
        document = func.to_tsvector(config, RagChunk.content)
        ts_query = func.plainto_tsquery(config, query)
        rank = func.ts_rank_cd(document, ts_query)
        acl = sql_cast(RagDocument.acl, JSONB)
        statement = (
            select(
                RagChunk.id,
                RagChunk.content,
                RagChunk.chunk_metadata,
                rank.label("score"),
            )
            .join(RagDocument, RagDocument.id == RagChunk.document_id)
            .where(
                RagChunk.tenant_id == tenant_id,
                RagChunk.collection == collection,
                RagDocument.tenant_id == tenant_id,
                RagDocument.collection == collection,
                acl_predicate(acl, retrieval_query),
                document.op("@@")(ts_query),
            )
            .order_by(rank.desc(), RagChunk.id.asc())
            .limit(limit)
        )
        if similarity_threshold > 0:
            statement = statement.where(rank >= similarity_threshold)
        async with self._session_factory() as session:
            await set_rag_rls_context_values(
                session,
                tenant_id=tenant_id,
                user_id=principal_id,
                groups=groups,
            )
            rows = await session.execute(statement)
            return [
                DocumentSearchResult(
                    id=str(row.id),
                    content=str(row.content),
                    metadata=metadata_dict(row.chunk_metadata),
                    score=float(row.score) if row.score is not None else None,
                )
                for row in rows.all()
            ]

    async def delete_documents(
        self,
        *,
        tenant_id: str,
        collection: str,
        ids: Sequence[str],
    ) -> int:
        async with self._session_factory() as session:
            async with session.begin():
                await set_rag_rls_context_values(
                    session, tenant_id=tenant_id, user_id="rag_document_store"
                )
                chunk_result = await session.execute(
                    delete(RagChunk)
                    .where(
                        RagChunk.tenant_id == tenant_id,
                        RagChunk.collection == collection,
                        RagChunk.id.in_(ids),
                    )
                    .returning(RagChunk.id)
                )
                document_result = await session.execute(
                    delete(RagDocument)
                    .where(
                        RagDocument.tenant_id == tenant_id,
                        RagDocument.collection == collection,
                        RagDocument.id.in_(ids),
                    )
                    .returning(RagDocument.id)
                )
                return len(chunk_result.scalars().all()) + len(document_result.scalars().all())


def metadata_dict(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return cast(dict[str, Any], value)
    return {}
