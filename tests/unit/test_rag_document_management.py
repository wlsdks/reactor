from __future__ import annotations

from datetime import UTC, datetime

from reactor.persistence.rag_ingest_store import checksum
from reactor.rag.document_management import (
    CONTENT_HASH_KEY,
    DEFAULT_DOCUMENT_COLLECTION,
    MANUAL_DOCUMENT_SOURCE_TYPE,
    ManagedDocumentInput,
    managed_chunk_records_to_langchain_documents,
    prepare_embedded_managed_document_records,
    prepare_managed_document_records,
    split_document_content,
)


def test_prepare_managed_document_records_preserves_metadata_acl_and_content_hash() -> None:
    now = datetime(2026, 6, 27, tzinfo=UTC)

    source, document, chunks = prepare_managed_document_records(
        ManagedDocumentInput(
            content="Title\nBody",
            metadata={
                "source": "upload",
                "acl": {"visibility": "public", "users": ["user_1"]},
            },
        ),
        tenant_id="tenant_1",
        collection=DEFAULT_DOCUMENT_COLLECTION,
        now=now,
    )

    assert source.tenant_id == "tenant_1"
    assert source.collection == DEFAULT_DOCUMENT_COLLECTION
    assert source.source_type == MANUAL_DOCUMENT_SOURCE_TYPE
    assert document.source_id == source.id
    assert document.title == "Title"
    assert document.acl == {"visibility": "public", "users": ["user_1"], "groups": []}
    assert document.metadata[CONTENT_HASH_KEY] == checksum("Title\nBody")
    assert chunks[0].document_id == document.id
    assert chunks[0].content == "Title\nBody"
    assert chunks[0].metadata["parent_document_id"] == document.id


def test_managed_chunk_records_convert_to_langchain_documents_with_canonical_metadata() -> None:
    now = datetime(2026, 6, 27, tzinfo=UTC)
    _source, document, chunks = prepare_managed_document_records(
        ManagedDocumentInput(
            content="Title\nBody",
            metadata={
                "source_uri": "s3://docs/title.md",
                "acl": {"visibility": "tenant"},
            },
        ),
        tenant_id="tenant_1",
        collection="docs",
        now=now,
    )

    langchain_documents = managed_chunk_records_to_langchain_documents(chunks)

    assert len(langchain_documents) == 1
    assert langchain_documents[0].id == f"{document.id}:0"
    assert langchain_documents[0].page_content == "Title\nBody"
    assert langchain_documents[0].metadata["tenant_id"] == "tenant_1"
    assert langchain_documents[0].metadata["collection"] == "docs"
    assert langchain_documents[0].metadata["document_id"] == document.id
    assert langchain_documents[0].metadata["chunk_index"] == 0
    assert langchain_documents[0].metadata["content_hash"] == checksum("Title\nBody")
    assert langchain_documents[0].metadata["parent_document_id"] == document.id
    assert langchain_documents[0].metadata["acl"] == {
        "visibility": "tenant",
        "users": [],
        "groups": [],
    }
    assert langchain_documents[0].metadata["acl_visibility"] == "tenant"


def test_prepare_managed_document_records_overrides_untrusted_provenance_metadata() -> None:
    now = datetime(2026, 6, 27, tzinfo=UTC)

    source, document, chunks = prepare_managed_document_records(
        ManagedDocumentInput(
            content="Executive salary bands",
            metadata={
                "source_uri": "s3://attacker/spoofed.md",
                "source_type": "external-crawl",
                "content_hash": "spoofed_hash",
                "acl_hash": "spoofed_acl",
                "acl_visibility": "private",
                "acl_users": ["attacker"],
                "acl_groups": ["executive"],
                "acl": {"visibility": "tenant"},
            },
        ),
        tenant_id="tenant_1",
        collection="docs",
        now=now,
    )

    assert source.source_uri.startswith("manual://documents/")
    assert source.source_type == MANUAL_DOCUMENT_SOURCE_TYPE
    assert source.metadata["source_uri"] == source.source_uri
    assert source.metadata["source_type"] == MANUAL_DOCUMENT_SOURCE_TYPE
    assert source.metadata[CONTENT_HASH_KEY] == checksum("Executive salary bands")
    assert source.metadata["acl_visibility"] == "tenant"
    assert source.metadata["acl_users"] == []
    assert source.metadata["acl_groups"] == []
    assert document.metadata["source_uri"] == source.source_uri
    assert chunks[0].metadata["source_uri"] == source.source_uri


def test_prepare_managed_document_records_rejects_missing_acl() -> None:
    now = datetime(2026, 6, 27, tzinfo=UTC)

    try:
        prepare_managed_document_records(
            ManagedDocumentInput(content="Executive salary bands", metadata={}),
            tenant_id="tenant_1",
            collection="docs",
            now=now,
        )
    except ValueError as error:
        assert str(error) == "Document ACL is required"
    else:
        raise AssertionError("documents without explicit ACL should fail closed")


def test_prepare_managed_document_records_rejects_malformed_acl_subjects() -> None:
    now = datetime(2026, 6, 27, tzinfo=UTC)

    for acl in (
        {"visibility": "private", "users": "ceo_1"},
        {"visibility": "private", "groups": "executive"},
        {"visibility": "private", "users": [123]},
        {"visibility": "private", "groups": [None]},
        {"visibility": "private", "users": [" "]},
        {"visibility": "private", "groups": [""]},
    ):
        try:
            prepare_managed_document_records(
                ManagedDocumentInput(content="Executive salary bands", metadata={"acl": acl}),
                tenant_id="tenant_1",
                collection="docs",
                now=now,
            )
        except ValueError as error:
            assert str(error) == "Document ACL users and groups must be lists of strings"
        else:
            raise AssertionError("documents with malformed ACL subjects should fail closed")


def test_private_acl_metadata_adds_searchable_user_and_group_markers() -> None:
    now = datetime(2026, 6, 27, tzinfo=UTC)
    _source, _document, chunks = prepare_managed_document_records(
        ManagedDocumentInput(
            content="Executive salary bands",
            metadata={
                "acl": {
                    "visibility": "private",
                    "users": ["ceo_1"],
                    "groups": ["executive"],
                }
            },
        ),
        tenant_id="tenant_1",
        collection="docs",
        now=now,
    )

    assert chunks[0].metadata["acl_visibility"] == "private"
    assert chunks[0].metadata["acl_users"] == ["ceo_1"]
    assert chunks[0].metadata["acl_groups"] == ["executive"]
    assert (
        chunks[0].metadata[
            "acl_user_36871ea355450eb18ef70c7f22e9872b550d7658053c805fc72de3b14600115c"
        ]
        == "1"
    )
    assert (
        chunks[0].metadata[
            "acl_group_180b988a36f655a375c5eadb524e0364aa1acd22c07568c1789235ae54a5514a"
        ]
        == "1"
    )


async def test_prepare_embedded_managed_document_records_embeds_each_chunk() -> None:
    now = datetime(2026, 6, 27, tzinfo=UTC)
    provider = FakeEmbeddingProvider()

    _source, _document, chunks = await prepare_embedded_managed_document_records(
        ManagedDocumentInput(
            content="alphabeta",
            metadata={"title": "Notes", "acl": {"visibility": "tenant"}},
        ),
        tenant_id="tenant_1",
        collection="docs",
        now=now,
        embedding_provider=provider,
        max_chunk_chars=5,
        chunk_overlap=0,
    )

    assert provider.queries == ["alpha", "beta"]
    assert [chunk.embedding for chunk in chunks] == [[5.0], [4.0]]


def test_split_document_content_uses_overlap_for_large_documents() -> None:
    chunks = split_document_content("a" * 4500, max_chars=4000, overlap=200)

    assert len(chunks) == 2
    assert len(chunks[0]) == 4000
    assert len(chunks[1]) == 700


def test_split_document_content_rejects_blank_content() -> None:
    try:
        split_document_content("  ")
    except ValueError as error:
        assert str(error) == "Document content is required"
    else:
        raise AssertionError("blank document content should fail")


class FakeEmbeddingProvider:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def embed_query(self, text: str) -> list[float]:
        self.queries.append(text)
        return [float(len(text))]
