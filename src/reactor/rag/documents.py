from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Protocol, cast

from langchain_core.documents import Document


class RagAclFilterQuery(Protocol):
    @property
    def tenant_id(self) -> str: ...

    @property
    def collection(self) -> str: ...

    @property
    def principal_id(self) -> str: ...

    @property
    def groups(self) -> tuple[str, ...]: ...

    def validate(self) -> None: ...


@dataclass(frozen=True)
class RagChunkCandidate:
    tenant_id: str
    collection: str
    document_id: str
    chunk_index: int
    content: str
    content_hash: str
    metadata: Mapping[str, Any]

    def acl(self) -> Mapping[str, Any]:
        value = self.metadata.get("acl", {})
        return cast(Mapping[str, Any], value) if isinstance(value, Mapping) else {}

    def validate(self) -> None:
        for field_name, value in (
            ("tenant_id", self.tenant_id),
            ("collection", self.collection),
            ("document_id", self.document_id),
            ("content", self.content),
            ("content_hash", self.content_hash),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} is required")
        if self.chunk_index < 0:
            raise ValueError("chunk_index must be non-negative")


def build_tenant_acl_filter(tenant_id: str, collection: str) -> dict[str, str]:
    if not tenant_id.strip():
        raise ValueError("tenant_id is required")
    if not collection.strip():
        raise ValueError("collection is required")
    return {"tenant_id": tenant_id, "collection": collection}


def build_langchain_pgvector_acl_filter(query: RagAclFilterQuery) -> dict[str, object]:
    query.validate()
    private_principal_filters: list[dict[str, str]] = [
        {acl_subject_marker_key("user", query.principal_id): "1"}
    ]
    private_principal_filters.extend(
        {acl_subject_marker_key("group", group): "1"} for group in query.groups
    )
    return {
        "$and": [
            {"tenant_id": query.tenant_id},
            {"collection": query.collection},
            {
                "$or": [
                    {"acl_visibility": {"$in": ["public", "tenant"]}},
                    {
                        "$and": [
                            {"acl_visibility": "private"},
                            {"$or": private_principal_filters},
                        ]
                    },
                ]
            },
        ]
    }


def acl_subject_marker_key(subject_type: str, subject_id: str) -> str:
    normalized_type = subject_type.strip().lower()
    normalized_id = subject_id.strip()
    if normalized_type not in {"user", "group"}:
        raise ValueError("subject_type must be user or group")
    if not normalized_id:
        raise ValueError("subject_id is required")
    return f"acl_{normalized_type}_{sha256(normalized_id.encode()).hexdigest()}"


def rag_chunk_to_langchain_document(chunk: RagChunkCandidate) -> Document:
    chunk.validate()
    metadata = dict(chunk.metadata)
    metadata.update(
        {
            "tenant_id": chunk.tenant_id,
            "collection": chunk.collection,
            "document_id": chunk.document_id,
            "chunk_index": chunk.chunk_index,
            "content_hash": chunk.content_hash,
        }
    )
    return Document(
        id=langchain_document_id(chunk.document_id, chunk.chunk_index),
        page_content=chunk.content,
        metadata=metadata,
    )


def langchain_document_to_chunk_candidate(document: Document) -> RagChunkCandidate:
    metadata = dict(document.metadata)
    chunk = RagChunkCandidate(
        tenant_id=required_metadata_text(metadata, "tenant_id"),
        collection=required_metadata_text(metadata, "collection"),
        document_id=required_metadata_text(metadata, "document_id"),
        chunk_index=required_metadata_int(metadata, "chunk_index"),
        content=document.page_content,
        content_hash=required_metadata_text(metadata, "content_hash"),
        metadata=metadata,
    )
    chunk.validate()
    return chunk


def langchain_document_id(document_id: str, chunk_index: int) -> str:
    return f"{document_id}:{chunk_index}"


def required_metadata_text(metadata: Mapping[str, object], key: str) -> str:
    value = metadata.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} metadata is required")
    return value


def required_metadata_int(metadata: Mapping[str, object], key: str) -> int:
    value = metadata.get(key)
    if not isinstance(value, int):
        raise ValueError(f"{key} metadata is required")
    return value
