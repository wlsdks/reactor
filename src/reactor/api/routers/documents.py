from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Protocol, cast

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import JSONResponse

from reactor.api.auth import require_any_admin
from reactor.api.schemas.documents import (
    AddDocumentRequest,
    BatchAddDocumentRequest,
    BatchDocumentResponse,
    DeleteDocumentRequest,
    DocumentResponse,
    SearchDocumentRequest,
    SearchResultResponse,
)
from reactor.auth.rbac import AuthPrincipal
from reactor.core.container import AppContainer
from reactor.persistence.rag_ingest_store import checksum
from reactor.providers.embeddings import EmbeddingProvider
from reactor.rag.document_management import (
    DEFAULT_DOCUMENT_COLLECTION,
    ManagedDocument,
    ManagedDocumentInput,
    prepare_embedded_managed_document_records,
    prepare_managed_document_records,
)

router = APIRouter(tags=["documents"])
DUPLICATE_ERROR_MESSAGE = "Document with identical content already exists"


class RagDocumentStore(Protocol):
    async def list_documents(
        self,
        *,
        tenant_id: str,
        collection: str,
        limit: int,
        principal_id: str,
        groups: tuple[str, ...],
    ) -> list[Any]: ...

    async def find_duplicate_content(
        self,
        *,
        tenant_id: str,
        collection: str,
        content_hash: str,
    ) -> str | None: ...

    async def save_document(
        self,
        *,
        source: Any,
        document: Any,
        chunks: list[Any],
    ) -> ManagedDocument: ...

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
    ) -> list[Any]: ...

    async def delete_documents(
        self,
        *,
        tenant_id: str,
        collection: str,
        ids: list[str],
    ) -> int: ...


def get_container(request: Request) -> AppContainer:
    return cast(AppContainer, request.app.state.reactor)


@router.get(
    "/api/documents",
    response_model=list[SearchResultResponse],
    response_model_by_alias=True,
)
@router.get(
    "/v1/documents",
    response_model=list[SearchResultResponse],
    response_model_by_alias=True,
)
async def list_documents(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
    limit: int = Query(default=100, ge=1, le=1000),
    collection: str = DEFAULT_DOCUMENT_COLLECTION,
) -> list[SearchResultResponse]:
    store = optional_rag_document_store(request)
    if store is None:
        return []
    rows = await store.list_documents(
        tenant_id=principal.tenant_id,
        collection=collection,
        limit=limit,
        principal_id=principal.user_id,
        groups=principal.groups,
    )
    return [search_result_response(row) for row in rows]


@router.post(
    "/api/documents",
    response_model=DocumentResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/v1/documents",
    response_model=DocumentResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
async def add_document(
    request: Request,
    body: AddDocumentRequest,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
    collection: str = DEFAULT_DOCUMENT_COLLECTION,
) -> DocumentResponse | JSONResponse:
    store = require_rag_document_store(request)
    if isinstance(store, JSONResponse):
        return store
    existing_id = await store.find_duplicate_content(
        tenant_id=principal.tenant_id,
        collection=collection,
        content_hash=checksum(body.content),
    )
    if existing_id is not None:
        return duplicate_conflict(existing_id)
    managed = await save_managed_document(
        store=store,
        embedding_provider=optional_embedding_provider(request),
        tenant_id=principal.tenant_id,
        collection=collection,
        body=body,
    )
    return document_response(managed)


@router.post(
    "/api/documents/batch",
    response_model=BatchDocumentResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/v1/documents/batch",
    response_model=BatchDocumentResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
async def add_documents(
    request: Request,
    body: BatchAddDocumentRequest,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
    collection: str = DEFAULT_DOCUMENT_COLLECTION,
) -> BatchDocumentResponse | JSONResponse:
    store = require_rag_document_store(request)
    if isinstance(store, JSONResponse):
        return store
    for document in body.documents:
        existing_id = await store.find_duplicate_content(
            tenant_id=principal.tenant_id,
            collection=collection,
            content_hash=checksum(document.content),
        )
        if existing_id is not None:
            return duplicate_conflict(existing_id)

    saved = [
        await save_managed_document(
            store=store,
            embedding_provider=optional_embedding_provider(request),
            tenant_id=principal.tenant_id,
            collection=collection,
            body=document,
        )
        for document in body.documents
    ]
    return BatchDocumentResponse(
        count=len(saved),
        totalChunks=sum(document.chunk_count for document in saved),
        ids=[document.document_id for document in saved],
    )


@router.post(
    "/api/documents/search",
    response_model=list[SearchResultResponse],
    response_model_by_alias=True,
)
@router.post(
    "/v1/documents/search",
    response_model=list[SearchResultResponse],
    response_model_by_alias=True,
)
async def search_documents(
    request: Request,
    body: SearchDocumentRequest,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
    collection: str = DEFAULT_DOCUMENT_COLLECTION,
) -> list[SearchResultResponse]:
    store = optional_rag_document_store(request)
    if store is None:
        return []
    rows = await store.search_documents(
        tenant_id=principal.tenant_id,
        collection=collection,
        query=body.query,
        limit=body.topK or 5,
        similarity_threshold=body.similarityThreshold or 0.0,
        principal_id=principal.user_id,
        groups=principal.groups,
    )
    return [search_result_response(row) for row in rows]


@router.delete(
    "/api/documents",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
@router.delete(
    "/v1/documents",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_documents(
    request: Request,
    body: DeleteDocumentRequest,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
    collection: str = DEFAULT_DOCUMENT_COLLECTION,
) -> Response | JSONResponse:
    store = require_rag_document_store(request)
    if isinstance(store, JSONResponse):
        return store
    await store.delete_documents(
        tenant_id=principal.tenant_id,
        collection=collection,
        ids=body.ids,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def save_managed_document(
    *,
    store: RagDocumentStore,
    embedding_provider: EmbeddingProvider | None,
    tenant_id: str,
    collection: str,
    body: AddDocumentRequest,
) -> ManagedDocument:
    metadata = dict(body.metadata or {})
    metadata["acl"] = body.acl.model_dump(exclude_defaults=True)
    input_document = ManagedDocumentInput(content=body.content, metadata=metadata)
    now = datetime.now(UTC)
    if embedding_provider is None:
        source, document, chunks = prepare_managed_document_records(
            input_document,
            tenant_id=tenant_id,
            collection=collection,
            now=now,
        )
    else:
        try:
            source, document, chunks = await prepare_embedded_managed_document_records(
                input_document,
                tenant_id=tenant_id,
                collection=collection,
                now=now,
                embedding_provider=embedding_provider,
            )
        except Exception:
            source, document, chunks = prepare_managed_document_records(
                input_document,
                tenant_id=tenant_id,
                collection=collection,
                now=now,
            )
    return await store.save_document(source=source, document=document, chunks=chunks)


def optional_rag_document_store(request: Request) -> RagDocumentStore | None:
    container = get_container(request)
    accessor = getattr(container, "rag_document_store", None)
    return accessor() if accessor is not None else None


def optional_embedding_provider(request: Request) -> EmbeddingProvider | None:
    container = get_container(request)
    accessor = getattr(container, "embedding_provider", None)
    return accessor() if accessor is not None else None


def require_rag_document_store(request: Request) -> RagDocumentStore | JSONResponse:
    store = optional_rag_document_store(request)
    if store is None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error": "RAG VectorStore not configured"},
        )
    return store


def duplicate_conflict(existing_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"error": DUPLICATE_ERROR_MESSAGE, "existingId": existing_id},
    )


def document_response(document: ManagedDocument) -> DocumentResponse:
    return DocumentResponse(
        id=document.document_id,
        content=document.content,
        metadata=document.metadata,
        chunkCount=document.chunk_count,
        chunkIds=document.chunk_ids if document.chunk_count > 1 else [],
    )


def search_result_response(row: Any) -> SearchResultResponse:
    return SearchResultResponse(
        id=str(row.id),
        content=str(row.content),
        metadata=dict(row.metadata),
        score=row.score,
    )
