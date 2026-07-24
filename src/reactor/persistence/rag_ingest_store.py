from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reactor.persistence.models import RagChunk, RagDocument, RagSource
from reactor.persistence.repositories.rag_postgres import set_rag_rls_context_values
from reactor.providers.embeddings import EmbeddingProvider
from reactor.slack.faq_ingestion import SLACK_FAQ_COLLECTION, FaqDocument


@dataclass(frozen=True)
class RagSourceMigrationRecord:
    id: str
    tenant_id: str
    collection: str
    source_uri: str
    source_type: str
    checksum: str
    metadata: dict[str, Any]
    created_at: datetime

    def validate(self) -> None:
        require_non_blank(
            ("id", self.id),
            ("tenant_id", self.tenant_id),
            ("collection", self.collection),
            ("source_uri", self.source_uri),
            ("source_type", self.source_type),
            ("checksum", self.checksum),
        )


@dataclass(frozen=True)
class RagDocumentMigrationRecord:
    id: str
    tenant_id: str
    source_id: str
    collection: str
    title: str
    version: str
    acl: dict[str, Any]
    metadata: dict[str, Any]
    created_at: datetime

    def validate(self) -> None:
        require_non_blank(
            ("id", self.id),
            ("tenant_id", self.tenant_id),
            ("source_id", self.source_id),
            ("collection", self.collection),
            ("title", self.title),
            ("version", self.version),
        )


@dataclass(frozen=True)
class RagChunkMigrationRecord:
    id: str
    tenant_id: str
    document_id: str
    collection: str
    chunk_index: int
    content: str
    content_hash: str
    embedding: list[float] | None
    metadata: dict[str, Any]
    created_at: datetime

    def validate(self) -> None:
        require_non_blank(
            ("id", self.id),
            ("tenant_id", self.tenant_id),
            ("document_id", self.document_id),
            ("collection", self.collection),
            ("content_hash", self.content_hash),
        )


@dataclass(frozen=True)
class RagStatsRecord:
    collection: str
    source_count: int
    document_count: int
    chunk_count: int
    embedded_chunk_count: int


class SqlAlchemyFaqDocumentSink:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._embedding_provider = embedding_provider

    async def add_documents(
        self,
        documents: Sequence[FaqDocument],
        *,
        tenant_id: str,
    ) -> int:
        chunk_count = 0
        async with self._session_factory() as session:
            async with session.begin():
                await set_rag_rls_context_values(session, tenant_id=tenant_id, user_id="rag_ingest")
                for document in documents:
                    embedding = await self._embed_document(document)
                    source_id = await session.scalar(
                        build_faq_source_upsert(document, tenant_id=tenant_id)
                    )
                    if source_id is None:
                        raise RuntimeError("FAQ RAG source upsert did not return an id")
                    document_id = await session.scalar(
                        build_faq_document_upsert(
                            document,
                            tenant_id=tenant_id,
                            source_id=source_id,
                        )
                    )
                    if document_id is None:
                        raise RuntimeError("FAQ RAG document upsert did not return an id")
                    chunk_id = await session.scalar(
                        build_faq_chunk_upsert(
                            document,
                            tenant_id=tenant_id,
                            document_id=document_id,
                            embedding=embedding,
                        )
                    )
                    if chunk_id is None:
                        raise RuntimeError("FAQ RAG chunk upsert did not return an id")
                    chunk_count += 1
        return chunk_count

    async def _embed_document(self, document: FaqDocument) -> list[float] | None:
        if self._embedding_provider is None:
            return None
        return await self._embedding_provider.embed_query(document.content)

    async def save_source(self, record: RagSourceMigrationRecord) -> str:
        record.validate()
        async with self._session_factory() as session:
            async with session.begin():
                await set_rag_rls_context_values(
                    session, tenant_id=record.tenant_id, user_id="rag_ingest"
                )
                await session.execute(build_rag_source_migration_upsert(record))
        return record.id

    async def save_document(self, record: RagDocumentMigrationRecord) -> str:
        record.validate()
        async with self._session_factory() as session:
            async with session.begin():
                await set_rag_rls_context_values(
                    session, tenant_id=record.tenant_id, user_id="rag_ingest"
                )
                await session.execute(build_rag_document_migration_upsert(record))
        return record.id

    async def save_chunk(self, record: RagChunkMigrationRecord) -> str:
        record.validate()
        async with self._session_factory() as session:
            async with session.begin():
                await set_rag_rls_context_values(
                    session, tenant_id=record.tenant_id, user_id="rag_ingest"
                )
                await session.execute(build_rag_chunk_migration_upsert(record))
        return record.id

    async def stats_by_collection(self, *, tenant_id: str) -> list[RagStatsRecord]:
        source_counts = await self._source_counts(tenant_id=tenant_id)
        document_counts = await self._document_counts(tenant_id=tenant_id)
        chunk_counts = await self._chunk_counts(tenant_id=tenant_id)
        collections = sorted(
            set(source_counts.keys()) | set(document_counts.keys()) | set(chunk_counts.keys())
        )
        return [
            RagStatsRecord(
                collection=collection,
                source_count=source_counts.get(collection, 0),
                document_count=document_counts.get(collection, 0),
                chunk_count=chunk_counts.get(collection, (0, 0))[0],
                embedded_chunk_count=chunk_counts.get(collection, (0, 0))[1],
            )
            for collection in collections
        ]

    async def rag_analytics_status_summary(self, *, tenant_id: str) -> list[dict[str, object]]:
        async with self._session_factory() as session:
            await set_rag_rls_context_values(session, tenant_id=tenant_id, user_id="rag_analytics")
            rows = await session.execute(
                select(
                    func.count(RagSource.id).label("source_count"),
                    func.max(RagSource.created_at).label("latest_captured"),
                ).where(RagSource.tenant_id == tenant_id)
            )
            row = rows.one()
        count = int(row.source_count or 0)
        if count == 0:
            return []
        return [
            {
                "status": "INGESTED",
                "count": count,
                "latest_captured": datetime_iso(row.latest_captured),
            }
        ]

    async def rag_analytics_by_channel(
        self, *, tenant_id: str, from_time: datetime
    ) -> list[dict[str, object]]:
        async with self._session_factory() as session:
            await set_rag_rls_context_values(session, tenant_id=tenant_id, user_id="rag_analytics")
            rows = await session.execute(
                select(
                    RagSource.__table__.c.metadata,
                    RagSource.__table__.c.created_at,
                ).where(
                    RagSource.tenant_id == tenant_id,
                    RagSource.created_at > from_time,
                )
            )
            records = list(rows.all())
        buckets: dict[str, int] = {}
        for metadata, _created_at in records:
            channel = channel_from_metadata(cast(dict[str, Any], metadata))
            buckets[channel] = buckets.get(channel, 0) + 1
        return [
            {
                "channel": channel,
                "candidate_count": count,
                "ingested": count,
                "pending": 0,
                "rejected": 0,
            }
            for channel, count in sorted(buckets.items(), key=lambda item: item[1], reverse=True)
        ]

    async def _source_counts(self, *, tenant_id: str) -> dict[str, int]:
        async with self._session_factory() as session:
            await set_rag_rls_context_values(session, tenant_id=tenant_id, user_id="rag_stats")
            rows = await session.execute(
                select(RagSource.collection, func.count(RagSource.id))
                .where(RagSource.tenant_id == tenant_id)
                .group_by(RagSource.collection)
            )
            return {str(collection): int(count) for collection, count in rows.all()}

    async def _document_counts(self, *, tenant_id: str) -> dict[str, int]:
        async with self._session_factory() as session:
            await set_rag_rls_context_values(session, tenant_id=tenant_id, user_id="rag_stats")
            rows = await session.execute(
                select(RagDocument.collection, func.count(RagDocument.id))
                .where(RagDocument.tenant_id == tenant_id)
                .group_by(RagDocument.collection)
            )
            return {str(collection): int(count) for collection, count in rows.all()}

    async def _chunk_counts(self, *, tenant_id: str) -> dict[str, tuple[int, int]]:
        async with self._session_factory() as session:
            await set_rag_rls_context_values(session, tenant_id=tenant_id, user_id="rag_stats")
            rows = await session.execute(
                select(
                    RagChunk.collection,
                    func.count(RagChunk.id),
                    func.count(RagChunk.embedding),
                )
                .where(RagChunk.tenant_id == tenant_id)
                .group_by(RagChunk.collection)
            )
            return {
                str(collection): (int(chunk_count), int(embedded_count))
                for collection, chunk_count, embedded_count in rows.all()
            }


def build_rag_source_migration_upsert(record: RagSourceMigrationRecord) -> Any:
    values = {
        "id": record.id,
        "tenant_id": record.tenant_id,
        "collection": record.collection,
        "source_uri": record.source_uri,
        "source_type": record.source_type,
        "checksum": record.checksum,
        "metadata": dict(record.metadata),
        "created_at": record.created_at,
    }
    return (
        insert(cast(Any, RagSource.__table__))
        .values(values)
        .on_conflict_do_update(
            constraint="uq_rag_sources_uri",
            set_={
                "collection": values["collection"],
                "source_type": values["source_type"],
                "checksum": values["checksum"],
                "metadata": values["metadata"],
            },
        )
    )


def build_rag_document_migration_upsert(record: RagDocumentMigrationRecord) -> Any:
    values = {
        "id": record.id,
        "tenant_id": record.tenant_id,
        "source_id": record.source_id,
        "collection": record.collection,
        "title": record.title,
        "version": record.version,
        "acl": dict(record.acl),
        "metadata": dict(record.metadata),
        "created_at": record.created_at,
    }
    return (
        insert(cast(Any, RagDocument.__table__))
        .values(values)
        .on_conflict_do_update(
            constraint="uq_rag_documents_version",
            set_={
                "collection": values["collection"],
                "title": values["title"],
                "acl": values["acl"],
                "metadata": values["metadata"],
            },
        )
    )


def build_rag_chunk_migration_upsert(record: RagChunkMigrationRecord) -> Any:
    values = {
        "id": record.id,
        "tenant_id": record.tenant_id,
        "document_id": record.document_id,
        "collection": record.collection,
        "chunk_index": record.chunk_index,
        "content": record.content,
        "content_hash": record.content_hash,
        "embedding": record.embedding,
        "metadata": dict(record.metadata),
        "created_at": record.created_at,
    }
    return (
        insert(cast(Any, RagChunk.__table__))
        .values(values)
        .on_conflict_do_update(
            constraint="uq_rag_chunks_document_index",
            set_={
                "content": values["content"],
                "content_hash": values["content_hash"],
                "embedding": values["embedding"],
                "metadata": values["metadata"],
            },
        )
    )


def channel_from_metadata(metadata: dict[str, Any]) -> str:
    channel = (
        metadata.get("channel_id") or metadata.get("channel") or metadata.get("slackChannelId")
    )
    return channel if isinstance(channel, str) and channel.strip() else "unknown"


def datetime_iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def faq_source_values(document: FaqDocument, *, tenant_id: str) -> dict[str, object]:
    source_uri = source_uri_for_document(document)
    return {
        "id": deterministic_rag_id("rag_src", f"{tenant_id}:{source_uri}"),
        "tenant_id": tenant_id,
        "collection": SLACK_FAQ_COLLECTION,
        "source_uri": source_uri,
        "source_type": "slack-faq",
        "checksum": checksum(document.content),
        "metadata": dict(document.metadata),
    }


def faq_document_values(
    document: FaqDocument,
    *,
    tenant_id: str,
    source_id: str,
) -> dict[str, object]:
    return {
        "id": deterministic_rag_id("rag_doc", f"{tenant_id}:{document.document_id}"),
        "tenant_id": tenant_id,
        "source_id": source_id,
        "collection": SLACK_FAQ_COLLECTION,
        "title": title_for_document(document),
        "version": version_for_document(document),
        "acl": {"visibility": "tenant"},
        "metadata": dict(document.metadata),
    }


def faq_chunk_values(
    document: FaqDocument,
    *,
    tenant_id: str,
    document_id: str,
    embedding: list[float] | None = None,
) -> dict[str, object]:
    return {
        "id": deterministic_rag_id("rag_chk", f"{tenant_id}:{document.document_id}:0"),
        "tenant_id": tenant_id,
        "document_id": document_id,
        "collection": SLACK_FAQ_COLLECTION,
        "chunk_index": 0,
        "content": document.content,
        "content_hash": checksum(document.content),
        "embedding": embedding,
        "metadata": dict(document.metadata),
    }


def build_faq_source_upsert(document: FaqDocument, *, tenant_id: str) -> Any:
    values = faq_source_values(document, tenant_id=tenant_id)
    return (
        insert(cast(Any, RagSource.__table__))
        .values(values)
        .on_conflict_do_update(
            constraint="uq_rag_sources_uri",
            set_={
                "collection": values["collection"],
                "source_type": values["source_type"],
                "checksum": values["checksum"],
                "metadata": values["metadata"],
            },
        )
        .returning(RagSource.__table__.c.id)
    )


def build_faq_document_upsert(
    document: FaqDocument,
    *,
    tenant_id: str,
    source_id: str,
) -> Any:
    values = faq_document_values(document, tenant_id=tenant_id, source_id=source_id)
    return (
        insert(cast(Any, RagDocument.__table__))
        .values(values)
        .on_conflict_do_update(
            constraint="uq_rag_documents_version",
            set_={
                "title": values["title"],
                "acl": values["acl"],
                "metadata": values["metadata"],
            },
        )
        .returning(RagDocument.__table__.c.id)
    )


def build_faq_chunk_upsert(
    document: FaqDocument,
    *,
    tenant_id: str,
    document_id: str,
    embedding: list[float] | None = None,
) -> Any:
    values = faq_chunk_values(
        document,
        tenant_id=tenant_id,
        document_id=document_id,
        embedding=embedding,
    )
    return (
        insert(cast(Any, RagChunk.__table__))
        .values(values)
        .on_conflict_do_update(
            constraint="uq_rag_chunks_document_index",
            set_={
                "content": values["content"],
                "content_hash": values["content_hash"],
                "embedding": values["embedding"],
                "metadata": values["metadata"],
            },
        )
        .returning(RagChunk.__table__.c.id)
    )


def deterministic_rag_id(prefix: str, value: str) -> str:
    return f"{prefix}_{sha256(value.encode()).hexdigest()[:32]}"


def checksum(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def source_uri_for_document(document: FaqDocument) -> str:
    value = document.metadata.get("source_key")
    if isinstance(value, str) and value.strip():
        return value
    return document.document_id


def version_for_document(document: FaqDocument) -> str:
    value = document.metadata.get("ts")
    if isinstance(value, str) and value.strip():
        return value
    return checksum(document.content)[:16]


def title_for_document(document: FaqDocument) -> str:
    channel_id = document.metadata.get("channel_id")
    ts = document.metadata.get("ts")
    if isinstance(channel_id, str) and isinstance(ts, str) and channel_id and ts:
        return f"Slack FAQ {channel_id} {ts}"
    return f"Slack FAQ {document.document_id}"


def require_non_blank(*fields: tuple[str, str]) -> None:
    for field_name, value in fields:
        if not value.strip():
            raise ValueError(f"{field_name} is required")
