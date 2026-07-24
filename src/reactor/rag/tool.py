from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol, cast

from reactor.kernel.citations import MAX_CITATION_EVIDENCE_ITEMS
from reactor.providers.embeddings import EmbeddingProvider
from reactor.rag.citations import Citation, build_citations, citation_source_uri
from reactor.rag.poisoning import (
    citation_id_for_document_chunk,
    detect_rag_poisoning,
    label_ranked_chunk_for_prompt,
)
from reactor.rag.retriever import RankedChunk, RetrievalQuery, principal_can_read
from reactor.tools.catalog import ToolSpec
from reactor.tools.execution import ToolExecutionRequest, ToolExecutionResult

RAG_TOOL_NAMESPACE = "Rag"
RAG_HYBRID_SEARCH_TOOL_NAME = "hybrid_search"
RAG_HYBRID_SEARCH_QUALIFIED_NAME = f"{RAG_TOOL_NAMESPACE}:{RAG_HYBRID_SEARCH_TOOL_NAME}"
MAX_RAG_TOOL_LIMIT = MAX_CITATION_EVIDENCE_ITEMS
MODEL_VISIBLE_METADATA_DENYLIST = frozenset(
    {
        "acl",
        "acl_proof",
        "acl_hash",
        "acl_visibility",
        "acl_users",
        "acl_groups",
    }
)


class RagRetriever(Protocol):
    async def retrieve(
        self,
        query: RetrievalQuery,
        embedding: Sequence[float],
    ) -> list[RankedChunk]: ...


def rag_hybrid_search_tool_spec(tenant_id: str) -> ToolSpec:
    return ToolSpec(
        tenant_id=tenant_id,
        namespace=RAG_TOOL_NAMESPACE,
        name=RAG_HYBRID_SEARCH_TOOL_NAME,
        description=(
            "Search tenant-approved RAG documents with PostgreSQL pgvector and full-text hybrid "
            "retrieval. Returns grounded chunks and citations."
        ),
        risk_level="read",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "User search query."},
                "collection": {
                    "type": "string",
                    "description": "RAG collection name. Defaults to docs.",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": MAX_RAG_TOOL_LIMIT,
                    "description": "Maximum number of chunks to return.",
                },
            },
            "required": ["query"],
        },
        output_schema={"type": "object"},
        enabled=True,
        requires_approval=False,
    )


class RagHybridSearchToolHandler:
    def __init__(
        self,
        retriever: RagRetriever,
        embedding_provider: EmbeddingProvider,
    ) -> None:
        self._retriever = retriever
        self._embedding_provider = embedding_provider

    async def __call__(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        if request.tool.qualified_name != RAG_HYBRID_SEARCH_QUALIFIED_NAME:
            return ToolExecutionResult.error(
                "unsupported_tool",
                f"unsupported RAG tool: {request.tool.qualified_name}",
            )
        payload = dict(request.input_payload)
        try:
            query_text = required_string(payload, "query")
            collection = optional_string(payload, "collection", default="docs")
            limit = optional_int(payload, "limit", default=5, maximum=MAX_RAG_TOOL_LIMIT)
        except ValueError as error:
            return ToolExecutionResult.error("invalid_input", str(error))
        embedding = await self._embedding_provider.embed_query(query_text)
        retrieval_query = RetrievalQuery(
            tenant_id=request.tenant_id,
            collection=collection,
            query=query_text,
            principal_id=request.user_id,
            groups=trusted_user_groups(request),
            limit=limit,
        )
        ranked = await self._retriever.retrieve(retrieval_query, embedding)
        ranked = [
            item
            for item in ranked
            if item.chunk.tenant_id == retrieval_query.tenant_id
            and item.chunk.collection == retrieval_query.collection
            and principal_can_read(
                item.chunk.acl(),
                retrieval_query.principal_id,
                retrieval_query.groups,
            )
        ][: retrieval_query.limit]
        return ToolExecutionResult.success(
            {
                "chunks": [ranked_chunk_payload(item) for item in ranked],
                "citations": [citation_payload(item) for item in build_citations(ranked)],
            }
        )


def ranked_chunk_payload(ranked: RankedChunk) -> dict[str, object]:
    poisoning = detect_rag_poisoning(ranked.chunk)
    return {
        "citation_id": citation_id_for_document_chunk(
            ranked.chunk.document_id,
            ranked.chunk.chunk_index,
        ),
        "source_uri": citation_source_uri(ranked.chunk.metadata, ranked.chunk.document_id),
        "document_id": ranked.chunk.document_id,
        "chunk_index": ranked.chunk.chunk_index,
        "content": ranked.chunk.content,
        "model_visible_text": label_ranked_chunk_for_prompt(ranked),
        "content_hash": ranked.chunk.content_hash,
        "score": ranked.score,
        "vector_rank": ranked.vector_rank,
        "keyword_rank": ranked.keyword_rank,
        "metadata": model_visible_chunk_metadata(ranked.chunk.metadata),
        "poisoning": {
            "flagged": poisoning.flagged,
            "reasons": list(poisoning.reasons),
        },
    }


def model_visible_chunk_metadata(metadata: Mapping[str, Any]) -> dict[str, object]:
    visible: dict[str, object] = {}
    for key, value in metadata.items():
        safe_key = str(key)
        if is_denied_model_visible_metadata_key(safe_key):
            continue
        safe_value = model_visible_metadata_value(value)
        if safe_value is not _REDACTED_METADATA:
            visible[safe_key] = safe_value
    return visible


_REDACTED_METADATA = object()


def is_denied_model_visible_metadata_key(key: str) -> bool:
    normalized = key.strip().lower()
    return normalized in MODEL_VISIBLE_METADATA_DENYLIST or normalized.startswith(
        ("acl_user_", "acl_group_")
    )


def model_visible_metadata_value(value: object) -> object:
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    if isinstance(value, Mapping):
        safe_mapping = model_visible_chunk_metadata(cast(Mapping[str, Any], value))
        return safe_mapping if safe_mapping else _REDACTED_METADATA
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        safe_items: list[object] = []
        for item in cast(Sequence[object], value):
            safe_item = model_visible_metadata_value(item)
            if safe_item is not _REDACTED_METADATA:
                safe_items.append(safe_item)
        return safe_items
    return _REDACTED_METADATA


def citation_payload(citation: Citation) -> dict[str, object]:
    return {
        "citation_id": citation_id_for_document_chunk(
            citation.document_id,
            citation.chunk_index,
        ),
        "source_uri": citation.source_uri,
        "document_id": citation.document_id,
        "chunk_index": citation.chunk_index,
        "content_hash": citation.content_hash,
        "acl_hash": str(citation.acl_proof.get("acl_hash", "")),
    }


def required_string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required")
    return value


def optional_string(payload: Mapping[str, Any], key: str, *, default: str) -> str:
    value = payload.get(key)
    if value is None:
        return default
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value


def optional_int(
    payload: Mapping[str, Any],
    key: str,
    *,
    default: int,
    maximum: int | None = None,
) -> int:
    value = payload.get(key)
    if value is None:
        return default
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{key} must be a positive integer")
    if maximum is not None and value > maximum:
        raise ValueError(f"{key} must be less than or equal to {maximum}")
    return value


def optional_string_tuple(payload: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, str):
        raise ValueError(f"{key} must be a list of strings")
    values = cast(Sequence[object], value)
    return tuple(str(item) for item in values if str(item).strip())


def trusted_user_groups(request: ToolExecutionRequest) -> tuple[str, ...]:
    return tuple(group.strip() for group in request.trusted_user_groups if group.strip())
