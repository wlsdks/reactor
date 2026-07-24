from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

import pytest
from sqlalchemy.dialects import postgresql

from reactor.persistence.rag_ingest_store import (
    SqlAlchemyFaqDocumentSink,
    build_faq_chunk_upsert,
    build_faq_document_upsert,
    build_faq_source_upsert,
    deterministic_rag_id,
    faq_chunk_values,
    faq_document_values,
    faq_source_values,
)
from reactor.slack.faq_ingestion import FaqDocument


def test_faq_document_values_preserve_slack_metadata_and_acl() -> None:
    document = FaqDocument(
        document_id="slack-faq:C123:1710000000.000100",
        content="Reactor FAQ 내용",
        metadata={
            "source": "slack-faq",
            "channel_id": "C123",
            "ts": "1710000000.000100",
            "source_key": "slack-faq:C123:1710000000.000100",
        },
    )

    source_values = faq_source_values(document, tenant_id="tenant_1")
    document_values = faq_document_values(
        document,
        tenant_id="tenant_1",
        source_id="source_1",
    )
    chunk_values = faq_chunk_values(document, tenant_id="tenant_1", document_id="doc_1")

    assert source_values["id"] == deterministic_rag_id(
        "rag_src", "tenant_1:slack-faq:C123:1710000000.000100"
    )
    assert source_values["collection"] == "slack-faq"
    assert source_values["source_type"] == "slack-faq"
    assert source_values["source_uri"] == "slack-faq:C123:1710000000.000100"
    assert document_values["collection"] == "slack-faq"
    assert document_values["title"] == "Slack FAQ C123 1710000000.000100"
    assert document_values["acl"] == {"visibility": "tenant"}
    assert chunk_values["chunk_index"] == 0
    assert chunk_values["content"] == "Reactor FAQ 내용"
    assert cast(dict[str, object], chunk_values["metadata"])["source"] == "slack-faq"
    assert chunk_values["embedding"] is None


def test_faq_upserts_target_existing_rag_constraints() -> None:
    document = FaqDocument(
        document_id="slack-faq:C123:1710000000.000100",
        content="Reactor FAQ 내용",
        metadata={"source_key": "slack-faq:C123:1710000000.000100"},
    )

    source_sql = str(
        build_faq_source_upsert(document, tenant_id="tenant_1").compile(
            dialect=postgresql.dialect()
        )
    )
    document_sql = str(
        build_faq_document_upsert(
            document,
            tenant_id="tenant_1",
            source_id="source_1",
        ).compile(dialect=postgresql.dialect())
    )
    chunk_sql = str(
        build_faq_chunk_upsert(document, tenant_id="tenant_1", document_id="doc_1").compile(
            dialect=postgresql.dialect()
        )
    )

    assert "uq_rag_sources_uri" in source_sql
    assert "uq_rag_documents_version" in document_sql
    assert "uq_rag_chunks_document_index" in chunk_sql
    assert "RETURNING rag_sources.id" in source_sql
    assert "RETURNING rag_documents.id" in document_sql
    assert "RETURNING rag_chunks.id" in chunk_sql


async def test_faq_document_sink_embeds_chunks_before_upsert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = FaqDocument(
        document_id="slack-faq:C123:1710000000.000100",
        content="Slack FAQ content that should be embedded",
        metadata={"source_key": "slack-faq:C123:1710000000.000100"},
    )
    session = FakeSession(scalar_results=["source_1", "doc_1", "chunk_1"])
    embedding_provider = RecordingEmbeddingProvider([[0.1, 0.2, 0.3]])
    captured_embeddings: list[list[float] | None] = []

    monkeypatch.setattr(
        "reactor.persistence.rag_ingest_store.build_faq_source_upsert",
        fake_source_upsert,
    )
    monkeypatch.setattr(
        "reactor.persistence.rag_ingest_store.build_faq_document_upsert",
        fake_document_upsert,
    )

    def capture_chunk_upsert(
        document: FaqDocument,
        *,
        tenant_id: str,
        document_id: str,
        embedding: list[float] | None = None,
    ) -> tuple[str, str, str, str, list[float] | None]:
        captured_embeddings.append(embedding)
        return ("chunk", document.document_id, tenant_id, document_id, embedding)

    monkeypatch.setattr(
        "reactor.persistence.rag_ingest_store.build_faq_chunk_upsert",
        capture_chunk_upsert,
    )

    sink = SqlAlchemyFaqDocumentSink(
        cast(Any, FakeSessionFactory(session)),
        embedding_provider=embedding_provider,
    )

    chunk_count = await sink.add_documents([document], tenant_id="tenant_1")

    assert chunk_count == 1
    assert embedding_provider.calls == ["Slack FAQ content that should be embedded"]
    assert captured_embeddings == [[0.1, 0.2, 0.3]]
    assert session.statements[-1] == (
        "chunk",
        "slack-faq:C123:1710000000.000100",
        "tenant_1",
        "doc_1",
        [0.1, 0.2, 0.3],
    )


def fake_source_upsert(
    document: FaqDocument,
    *,
    tenant_id: str,
) -> tuple[str, str, str]:
    return ("source", document.document_id, tenant_id)


def fake_document_upsert(
    document: FaqDocument,
    *,
    tenant_id: str,
    source_id: str,
) -> tuple[str, str, str, str]:
    return ("document", document.document_id, tenant_id, source_id)


class RecordingEmbeddingProvider:
    def __init__(self, embeddings: Sequence[Sequence[float]]) -> None:
        self._embeddings = [list(embedding) for embedding in embeddings]
        self.calls: list[str] = []

    async def embed_query(self, text: str) -> list[float]:
        self.calls.append(text)
        return self._embeddings.pop(0)


class FakeTransaction:
    async def __aenter__(self) -> FakeTransaction:
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None


class FakeSession:
    def __init__(self, *, scalar_results: Sequence[str]) -> None:
        self._scalar_results = list(scalar_results)
        self.statements: list[object] = []

    def begin(self) -> FakeTransaction:
        return FakeTransaction()

    async def execute(self, statement: object) -> None:
        self.statements.append(statement)

    async def scalar(self, statement: object) -> str | None:
        self.statements.append(statement)
        return self._scalar_results.pop(0)

    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None


class FakeSessionFactory:
    def __init__(self, session: FakeSession) -> None:
        self._session = session

    def __call__(self) -> FakeSession:
        return self._session
