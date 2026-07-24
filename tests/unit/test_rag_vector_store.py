from __future__ import annotations

from typing import Any

import pytest

from reactor.core.settings import Settings
from reactor.providers.embeddings import LangChainEmbeddingProvider
from reactor.rag.documents import acl_subject_marker_key
from reactor.rag.retriever import RetrievalQuery
from reactor.rag.vector_store import (
    AuthorizedLangChainPgVectorStore,
    LangChainPgVectorStoreFactory,
    pgvector_connection_url,
)


def test_pgvector_connection_url_uses_psycopg_driver() -> None:
    assert (
        pgvector_connection_url("postgresql://reactor:reactor@localhost:5432/reactor")
        == "postgresql+psycopg://reactor:reactor@localhost:5432/reactor"
    )


def test_embedding_provider_exposes_langchain_embeddings(monkeypatch: Any) -> None:
    expected_embeddings = object()

    def fake_init_embeddings(model: str, *, provider: str) -> object:
        assert model == "text-embedding-3-small"
        assert provider == "openai"
        return expected_embeddings

    monkeypatch.setattr(
        "reactor.providers.embeddings.LANGCHAIN_INIT_EMBEDDINGS",
        fake_init_embeddings,
    )

    provider = LangChainEmbeddingProvider(Settings())

    assert provider.langchain_embeddings() is expected_embeddings
    assert provider.langchain_embeddings() is expected_embeddings


def test_pgvector_factory_delegates_to_langchain_postgres_pgvector(monkeypatch: Any) -> None:
    calls: list[dict[str, object]] = []
    expected_store = object()
    embeddings = object()

    def fake_pgvector(**kwargs: object) -> object:
        calls.append(kwargs)
        return expected_store

    monkeypatch.setattr("reactor.rag.vector_store.LANGCHAIN_PGVECTOR", fake_pgvector)

    store = LangChainPgVectorStoreFactory().create(
        Settings(database_url="postgresql://reactor:reactor@localhost:5432/reactor"),
        embeddings=embeddings,
        collection_name="tenant_1_docs",
    )

    assert store is expected_store
    assert calls == [
        {
            "embeddings": embeddings,
            "connection": "postgresql+psycopg://reactor:reactor@localhost:5432/reactor",
            "collection_name": "tenant_1_docs",
            "embedding_length": 1536,
            "async_mode": True,
            "use_jsonb": True,
        }
    ]


def test_pgvector_factory_requires_database_url() -> None:
    with pytest.raises(ValueError, match="database_url is required"):
        LangChainPgVectorStoreFactory().create(Settings(database_url=None), embeddings=object())


async def test_authorized_pgvector_search_always_applies_acl_filter() -> None:
    raw_store = RecordingPgVectorStore()
    query = RetrievalQuery(
        tenant_id="tenant_1",
        collection="docs",
        query="executive salary",
        principal_id="employee_1",
        groups=("finance",),
        limit=3,
    )

    result = await AuthorizedLangChainPgVectorStore(raw_store).authorized_similarity_search(query)

    assert result == ["doc_public"]
    assert raw_store.retriever_calls == [
        {
            "search_kwargs": {
                "k": 3,
                "filter": {
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
                                                {acl_subject_marker_key("group", "finance"): "1"},
                                            ]
                                        },
                                    ]
                                },
                            ]
                        },
                    ]
                },
            },
            "query": "executive salary",
        }
    ]


class RecordingPgVectorStore:
    def __init__(self) -> None:
        self.retriever_calls: list[dict[str, object]] = []

    def as_retriever(self, *, search_kwargs: dict[str, object]) -> RecordingRetriever:
        return RecordingRetriever(self.retriever_calls, search_kwargs=search_kwargs)


class RecordingRetriever:
    def __init__(
        self,
        calls: list[dict[str, object]],
        *,
        search_kwargs: dict[str, object],
    ) -> None:
        self._calls = calls
        self._search_kwargs = search_kwargs

    async def ainvoke(self, query: str) -> list[str]:
        self._calls.append({"search_kwargs": self._search_kwargs, "query": query})
        return ["doc_public"]
