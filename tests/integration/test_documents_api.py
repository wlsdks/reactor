from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from httpx import ASGITransport, AsyncClient

from reactor.api.app import create_app
from reactor.core.settings import Settings
from reactor.persistence.rag_ingest_store import checksum
from reactor.rag.document_management import ManagedDocument

ADMIN_HEADERS = {
    "X-Reactor-User-Id": "admin_1",
    "X-Reactor-Tenant-Id": "tenant_1",
    "X-Reactor-Role": "ADMIN",
    "X-Reactor-Groups": "engineering,executive",
}
USER_HEADERS = {
    "X-Reactor-User-Id": "user_1",
    "X-Reactor-Tenant-Id": "tenant_1",
    "X-Reactor-Role": "USER",
}


async def test_documents_api_adds_lists_searches_and_deletes_admin_documents() -> None:
    store = FakeRagDocumentStore()
    app = create_app()
    app.state.reactor = FakeContainer(store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        added = await client.post(
            "/api/documents",
            headers=ADMIN_HEADERS,
            json={
                "content": "Reactor RAG document",
                "metadata": {"source": "test"},
                "acl": {"visibility": "tenant"},
            },
        )
        listed = await client.get("/api/documents", headers=ADMIN_HEADERS)
        searched = await client.post(
            "/v1/documents/search",
            headers=ADMIN_HEADERS,
            json={"query": "RAG", "topK": 5, "similarityThreshold": 0.0},
        )
        deleted = await client.request(
            "DELETE",
            "/api/documents",
            headers=ADMIN_HEADERS,
            json={"ids": [added.json()["id"]]},
        )

    assert added.status_code == 201
    assert added.json()["content"] == "Reactor RAG document"
    assert added.json()["metadata"]["content_hash"] == checksum("Reactor RAG document")
    assert added.json()["chunkCount"] == 1
    assert added.json()["chunkIds"] == []
    assert listed.status_code == 200
    assert listed.json()[0]["content"] == "Reactor RAG document"
    assert searched.status_code == 200
    assert searched.json()[0]["score"] == 1.0
    assert store.list_principals == [("admin_1", ("engineering", "executive"))]
    assert store.search_principals == [("admin_1", ("engineering", "executive"))]
    assert deleted.status_code == 204
    assert store.deleted_ids == [added.json()["id"]]


async def test_documents_api_embeds_chunks_when_container_has_embedding_provider() -> None:
    store = FakeRagDocumentStore()
    provider = FakeEmbeddingProvider()
    app = create_app()
    app.state.reactor = FakeContainer(store, embedding_provider=provider)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/documents",
            headers=ADMIN_HEADERS,
            json={
                "content": "Reactor RAG document",
                "metadata": {"source": "test"},
                "acl": {"visibility": "tenant"},
            },
        )

    assert response.status_code == 201
    assert provider.queries == ["Reactor RAG document"]
    assert store.saved_chunks[0][0].embedding == [20.0]


async def test_documents_api_accepts_first_class_acl_for_private_group_documents() -> None:
    store = FakeRagDocumentStore()
    app = create_app()
    app.state.reactor = FakeContainer(store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/documents",
            headers=ADMIN_HEADERS,
            json={
                "content": "Executive salary private note",
                "acl": {"visibility": "private", "groups": ["executive"]},
            },
        )

    assert response.status_code == 201
    assert response.json()["metadata"]["acl"] == {
        "visibility": "private",
        "users": [],
        "groups": ["executive"],
    }
    assert response.json()["metadata"]["acl_visibility"] == "private"
    assert response.json()["metadata"]["acl_groups"] == ["executive"]


async def test_documents_api_rejects_unknown_acl_visibility() -> None:
    store = FakeRagDocumentStore()
    app = create_app()
    app.state.reactor = FakeContainer(store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/documents",
            headers=ADMIN_HEADERS,
            json={
                "content": "Executive salary private note",
                "acl": {"visibility": "department"},
            },
        )

    assert response.status_code == 422


async def test_documents_api_rejects_missing_acl() -> None:
    store = FakeRagDocumentStore()
    app = create_app()
    app.state.reactor = FakeContainer(store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/documents",
            headers=ADMIN_HEADERS,
            json={"content": "Executive salary private note"},
        )

    assert response.status_code == 422


async def test_documents_api_saves_without_embeddings_when_embedding_provider_fails() -> None:
    store = FakeRagDocumentStore()
    app = create_app()
    app.state.reactor = FakeContainer(store, embedding_provider=RaisingEmbeddingProvider())
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/documents",
            headers=ADMIN_HEADERS,
            json={
                "content": "Reactor RAG document",
                "metadata": {"source": "test"},
                "acl": {"visibility": "tenant"},
            },
        )

    assert response.status_code == 201
    assert store.saved_chunks[0][0].embedding is None


async def test_documents_api_rejects_non_admin_and_duplicate_content() -> None:
    store = FakeRagDocumentStore(duplicates={checksum("same"): "existing-id"})
    app = create_app()
    app.state.reactor = FakeContainer(store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.post(
            "/api/documents",
            headers=USER_HEADERS,
            json={"content": "new", "acl": {"visibility": "tenant"}},
        )
        duplicate = await client.post(
            "/api/documents",
            headers=ADMIN_HEADERS,
            json={"content": "same", "acl": {"visibility": "tenant"}},
        )

    assert forbidden.status_code == 403
    assert duplicate.status_code == 409
    assert duplicate.json() == {
        "error": "Document with identical content already exists",
        "existingId": "existing-id",
    }


async def test_documents_batch_adds_each_document_and_reports_total_chunks() -> None:
    store = FakeRagDocumentStore()
    app = create_app()
    app.state.reactor = FakeContainer(store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/documents/batch",
            headers=ADMIN_HEADERS,
            json={
                "documents": [
                    {"content": "one", "acl": {"visibility": "tenant"}},
                    {"content": "two", "acl": {"visibility": "tenant"}},
                ]
            },
        )

    assert response.status_code == 201
    assert response.json()["count"] == 2
    assert response.json()["totalChunks"] == 2
    assert len(response.json()["ids"]) == 2
    assert len(store.documents) == 2


async def test_documents_api_returns_empty_for_read_without_rag_store_and_503_for_write() -> None:
    app = create_app()
    app.state.reactor = FakeContainer(None)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        listed = await client.get("/api/documents", headers=ADMIN_HEADERS)
        searched = await client.post(
            "/api/documents/search",
            headers=ADMIN_HEADERS,
            json={"query": "anything"},
        )
        added = await client.post(
            "/api/documents",
            headers=ADMIN_HEADERS,
            json={"content": "content", "acl": {"visibility": "tenant"}},
        )

    assert listed.status_code == 200
    assert listed.json() == []
    assert searched.status_code == 200
    assert searched.json() == []
    assert added.status_code == 503
    assert added.json()["error"] == "RAG VectorStore not configured"


class FakeContainer:
    def __init__(
        self,
        store: FakeRagDocumentStore | None,
        *,
        embedding_provider: Any | None = None,
    ) -> None:
        self.settings = Settings()
        self._store = store
        self._embedding_provider = embedding_provider

    def rag_document_store(self) -> FakeRagDocumentStore | None:
        return self._store

    def embedding_provider(self) -> FakeEmbeddingProvider | None:
        return self._embedding_provider


@dataclass
class FakeSearchRow:
    id: str
    content: str
    metadata: dict[str, Any]
    score: float | None


class FakeRagDocumentStore:
    def __init__(self, duplicates: dict[str, str] | None = None) -> None:
        self.duplicates = dict(duplicates or {})
        self.documents: list[ManagedDocument] = []
        self.deleted_ids: list[str] = []
        self.saved_chunks: list[list[Any]] = []
        self.list_principals: list[tuple[str, tuple[str, ...]]] = []
        self.search_principals: list[tuple[str, tuple[str, ...]]] = []

    async def list_documents(
        self,
        *,
        tenant_id: str,
        collection: str,
        limit: int,
        principal_id: str,
        groups: tuple[str, ...],
    ) -> list[FakeSearchRow]:
        del tenant_id, collection
        self.list_principals.append((principal_id, groups))
        return [
            FakeSearchRow(
                id=document.document_id,
                content=document.content,
                metadata=document.metadata,
                score=None,
            )
            for document in self.documents[:limit]
        ]

    async def find_duplicate_content(
        self,
        *,
        tenant_id: str,
        collection: str,
        content_hash: str,
    ) -> str | None:
        del tenant_id, collection
        return self.duplicates.get(content_hash)

    async def save_document(
        self,
        *,
        source: object,
        document: Any,
        chunks: list[Any],
    ) -> ManagedDocument:
        del source
        self.saved_chunks.append(chunks)
        document_id = str(document.id)
        metadata = dict(document.metadata)
        managed = ManagedDocument(
            document_id=document_id,
            content="\n".join(str(chunk.content) for chunk in chunks),
            metadata=metadata,
            chunk_ids=[str(chunk.id) for chunk in chunks],
        )
        self.documents.append(managed)
        return managed

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
    ) -> list[FakeSearchRow]:
        del tenant_id, collection, similarity_threshold
        self.search_principals.append((principal_id, groups))
        return [
            FakeSearchRow(
                id=document.document_id,
                content=document.content,
                metadata=document.metadata,
                score=1.0,
            )
            for document in self.documents
            if query.lower() in document.content.lower()
        ][:limit]

    async def delete_documents(
        self,
        *,
        tenant_id: str,
        collection: str,
        ids: list[str],
    ) -> int:
        del tenant_id, collection
        self.deleted_ids.extend(ids)
        before = len(self.documents)
        self.documents = [
            document for document in self.documents if document.document_id not in ids
        ]
        return before - len(self.documents)


class FakeEmbeddingProvider:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def embed_query(self, text: str) -> list[float]:
        self.queries.append(text)
        return [float(len(text))]


class RaisingEmbeddingProvider:
    async def embed_query(self, text: str) -> list[float]:
        del text
        raise RuntimeError("embedding provider unavailable")
