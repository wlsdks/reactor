from __future__ import annotations

from langchain_core.documents import Document

from reactor.rag.documents import (
    RagChunkCandidate,
    acl_subject_marker_key,
    build_langchain_pgvector_acl_filter,
    langchain_document_to_chunk_candidate,
    rag_chunk_to_langchain_document,
)
from reactor.rag.retriever import RetrievalQuery


def test_rag_chunk_candidate_round_trips_through_langchain_document() -> None:
    chunk = RagChunkCandidate(
        tenant_id="tenant_1",
        collection="docs",
        document_id="doc_1",
        chunk_index=2,
        content="Reactor uses LangGraph.",
        content_hash="sha256:chunk",
        metadata={
            "source_uri": "s3://docs/reactor.md",
            "acl": {"visibility": "private", "users": ["user_1"]},
            "acl_hash": "sha256:acl",
            "section": "runtime",
        },
    )

    document = rag_chunk_to_langchain_document(chunk)

    assert document.id == "doc_1:2"
    assert document.page_content == "Reactor uses LangGraph."
    assert document.metadata == {
        "source_uri": "s3://docs/reactor.md",
        "acl": {"visibility": "private", "users": ["user_1"]},
        "acl_hash": "sha256:acl",
        "section": "runtime",
        "tenant_id": "tenant_1",
        "collection": "docs",
        "document_id": "doc_1",
        "chunk_index": 2,
        "content_hash": "sha256:chunk",
    }

    restored = langchain_document_to_chunk_candidate(document)

    assert restored.tenant_id == chunk.tenant_id
    assert restored.collection == chunk.collection
    assert restored.document_id == chunk.document_id
    assert restored.chunk_index == chunk.chunk_index
    assert restored.content == chunk.content
    assert restored.content_hash == chunk.content_hash
    assert restored.metadata == document.metadata


def test_langchain_document_to_chunk_candidate_prefers_canonical_metadata_fields() -> None:
    document = Document(
        page_content="content",
        id="doc_from_id:7",
        metadata={
            "tenant_id": "tenant_1",
            "collection": "docs",
            "document_id": "doc_1",
            "chunk_index": 3,
            "content_hash": "sha256:chunk",
            "source_uri": "s3://docs/reactor.md",
        },
    )

    chunk = langchain_document_to_chunk_candidate(document)

    assert chunk.document_id == "doc_1"
    assert chunk.chunk_index == 3
    assert chunk.content_hash == "sha256:chunk"
    assert chunk.metadata["document_id"] == "doc_1"


def test_langchain_pgvector_acl_filter_is_tenant_scoped_and_fail_closed() -> None:
    query = RetrievalQuery(
        tenant_id="tenant_1",
        collection="docs",
        query="executive salary",
        principal_id="employee_1",
        groups=("engineering",),
    )

    assert build_langchain_pgvector_acl_filter(query) == {
        "$and": [
            {"tenant_id": "tenant_1"},
            {"collection": "docs"},
            {
                "$or": [
                    {"acl_visibility": {"$in": ["public", "tenant"]}},
                    {
                        "$and": [
                            {"acl_visibility": "private"},
                            {
                                "$or": [
                                    {acl_subject_marker_key("user", "employee_1"): "1"},
                                    {acl_subject_marker_key("group", "engineering"): "1"},
                                ]
                            },
                        ]
                    },
                ]
            },
        ]
    }
