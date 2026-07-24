from __future__ import annotations

from importlib import import_module
from typing import Any, Protocol, cast

from reactor.core.settings import Settings
from reactor.rag.documents import build_langchain_pgvector_acl_filter
from reactor.rag.retriever import RetrievalQuery

LANGCHAIN_POSTGRES_MODULE = cast(Any, import_module("langchain_postgres"))
LANGCHAIN_PGVECTOR: Any = LANGCHAIN_POSTGRES_MODULE.PGVector


class PgVectorStoreFactory(Protocol):
    def create(
        self,
        settings: Settings,
        *,
        embeddings: object,
        collection_name: str = "reactor_rag",
    ) -> Any: ...


class LangChainPgVectorStoreFactory:
    def create(
        self,
        settings: Settings,
        *,
        embeddings: object,
        collection_name: str = "reactor_rag",
    ) -> Any:
        if not settings.database_url:
            raise ValueError("database_url is required for PGVector")
        return LANGCHAIN_PGVECTOR(
            embeddings=embeddings,
            connection=pgvector_connection_url(settings.database_url),
            collection_name=collection_name,
            embedding_length=1536,
            async_mode=True,
            use_jsonb=True,
        )


class AuthorizedLangChainPgVectorStore:
    def __init__(self, vector_store: Any) -> None:
        self._vector_store = vector_store

    async def authorized_similarity_search(self, query: RetrievalQuery) -> list[Any]:
        query.validate()
        retriever = self._vector_store.as_retriever(
            search_kwargs={
                "k": query.limit,
                "filter": build_langchain_pgvector_acl_filter(query),
            }
        )
        return await retriever.ainvoke(query.query)


def pgvector_connection_url(database_url: str) -> str:
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url
