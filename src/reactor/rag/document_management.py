from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from hashlib import sha256
from typing import Any, cast
from uuid import uuid4

from langchain_core.documents import Document

from reactor.persistence.rag_ingest_store import (
    RagChunkMigrationRecord,
    RagDocumentMigrationRecord,
    RagSourceMigrationRecord,
    checksum,
    deterministic_rag_id,
)
from reactor.providers.embeddings import EmbeddingProvider
from reactor.rag.documents import (
    RagChunkCandidate,
    acl_subject_marker_key,
    rag_chunk_to_langchain_document,
)
from reactor.rag.text_splitters import split_text

DEFAULT_DOCUMENT_COLLECTION = "documents"
MANUAL_DOCUMENT_SOURCE_TYPE = "manual-document"
CONTENT_HASH_KEY = "content_hash"


@dataclass(frozen=True)
class ManagedDocumentInput:
    content: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class ManagedDocument:
    document_id: str
    content: str
    metadata: dict[str, Any]
    chunk_ids: list[str]

    @property
    def chunk_count(self) -> int:
        return len(self.chunk_ids)


@dataclass(frozen=True)
class DocumentSearchResult:
    id: str
    content: str
    metadata: dict[str, Any]
    score: float | None


def prepare_managed_document_records(
    document: ManagedDocumentInput,
    *,
    tenant_id: str,
    collection: str = DEFAULT_DOCUMENT_COLLECTION,
    now: datetime,
    max_chunk_chars: int = 4_000,
    chunk_overlap: int = 200,
) -> tuple[RagSourceMigrationRecord, RagDocumentMigrationRecord, list[RagChunkMigrationRecord]]:
    normalized_collection = collection.strip() or DEFAULT_DOCUMENT_COLLECTION
    document_id = f"rag_doc_{uuid4().hex}"
    source_uri = f"manual://documents/{document_id}"
    content_hash = checksum(document.content)
    metadata = dict(document.metadata)
    metadata[CONTENT_HASH_KEY] = content_hash
    metadata["source_uri"] = source_uri
    metadata["source_type"] = MANUAL_DOCUMENT_SOURCE_TYPE
    acl = document_acl(metadata)
    metadata["acl"] = acl
    metadata.update(flatten_acl_metadata(acl))
    chunks = split_document_content(
        document.content,
        max_chars=max_chunk_chars,
        overlap=chunk_overlap,
    )
    source = RagSourceMigrationRecord(
        id=deterministic_rag_id("rag_src", f"{tenant_id}:{source_uri}"),
        tenant_id=tenant_id,
        collection=normalized_collection,
        source_uri=source_uri,
        source_type=MANUAL_DOCUMENT_SOURCE_TYPE,
        checksum=content_hash,
        metadata=metadata,
        created_at=now,
    )
    rag_document = RagDocumentMigrationRecord(
        id=document_id,
        tenant_id=tenant_id,
        source_id=source.id,
        collection=normalized_collection,
        title=str(metadata.get("title") or first_line(document.content)),
        version=content_hash[:16],
        acl=acl,
        metadata=metadata,
        created_at=now,
    )
    rag_chunks = [
        RagChunkMigrationRecord(
            id=f"rag_chk_{sha256(f'{document_id}:{index}'.encode()).hexdigest()[:32]}",
            tenant_id=tenant_id,
            document_id=document_id,
            collection=normalized_collection,
            chunk_index=index,
            content=chunk,
            content_hash=checksum(chunk),
            embedding=None,
            metadata=metadata | {"parent_document_id": document_id},
            created_at=now,
        )
        for index, chunk in enumerate(chunks)
    ]
    return source, rag_document, rag_chunks


async def prepare_embedded_managed_document_records(
    document: ManagedDocumentInput,
    *,
    tenant_id: str,
    collection: str = DEFAULT_DOCUMENT_COLLECTION,
    now: datetime,
    embedding_provider: EmbeddingProvider,
    max_chunk_chars: int = 4_000,
    chunk_overlap: int = 200,
) -> tuple[RagSourceMigrationRecord, RagDocumentMigrationRecord, list[RagChunkMigrationRecord]]:
    source, rag_document, chunks = prepare_managed_document_records(
        document,
        tenant_id=tenant_id,
        collection=collection,
        now=now,
        max_chunk_chars=max_chunk_chars,
        chunk_overlap=chunk_overlap,
    )
    embedded_chunks = [
        replace(chunk, embedding=await embedding_provider.embed_query(chunk.content))
        for chunk in chunks
    ]
    return source, rag_document, embedded_chunks


def split_document_content(
    content: str,
    *,
    max_chars: int = 4_000,
    overlap: int = 200,
) -> list[str]:
    return split_text(content, max_chunk_chars=max_chars, chunk_overlap=overlap)


def managed_chunk_records_to_langchain_documents(
    chunks: list[RagChunkMigrationRecord],
) -> list[Document]:
    return [
        rag_chunk_to_langchain_document(
            RagChunkCandidate(
                tenant_id=chunk.tenant_id,
                collection=chunk.collection,
                document_id=chunk.document_id,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                content_hash=chunk.content_hash,
                metadata=chunk.metadata,
            )
        )
        for chunk in chunks
    ]


def document_acl(metadata: dict[str, Any]) -> dict[str, Any]:
    acl = metadata.get("acl")
    if isinstance(acl, dict):
        normalized = dict(cast(dict[str, Any], acl))
        visibility = str(normalized.get("visibility", "")).strip()
        if visibility not in {"public", "tenant", "private"}:
            raise ValueError("Document ACL visibility must be public, tenant, or private")
        normalized["visibility"] = visibility
        normalized["users"] = acl_subjects(normalized.get("users", ()))
        normalized["groups"] = acl_subjects(normalized.get("groups", ()))
        return normalized
    raise ValueError("Document ACL is required")


def flatten_acl_metadata(acl: dict[str, Any]) -> dict[str, object]:
    visibility = str(acl.get("visibility", "")).strip()
    if visibility not in {"public", "tenant", "private"}:
        raise ValueError("Document ACL visibility must be public, tenant, or private")
    users = tuple(acl_subjects(acl.get("users", ())))
    groups = tuple(acl_subjects(acl.get("groups", ())))
    metadata: dict[str, object] = {
        "acl_visibility": visibility,
        "acl_users": list(users),
        "acl_groups": list(groups),
    }
    metadata.update({acl_subject_marker_key("user", user): "1" for user in users})
    metadata.update({acl_subject_marker_key("group", group): "1" for group in groups})
    return metadata


def acl_subjects(value: object) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, Sequence) or isinstance(value, str):
        raise ValueError("Document ACL users and groups must be lists of strings")
    subjects: list[str] = []
    for item in cast(Sequence[object], value):
        if not isinstance(item, str):
            raise ValueError("Document ACL users and groups must be lists of strings")
        normalized = item.strip()
        if not normalized:
            raise ValueError("Document ACL users and groups must be lists of strings")
        subjects.append(normalized)
    return subjects


def first_line(content: str) -> str:
    line = next((line.strip() for line in content.splitlines() if line.strip()), "")
    return line[:200] or "Untitled document"
