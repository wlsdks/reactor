from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from reactor.rag.retriever import RankedChunk


@dataclass(frozen=True)
class Citation:
    source_uri: str
    document_id: str
    chunk_index: int
    content_hash: str
    acl_proof: dict[str, object]


def build_citations(ranked_chunks: list[RankedChunk]) -> list[Citation]:
    citations: list[Citation] = []
    for ranked in ranked_chunks:
        metadata = ranked.chunk.metadata
        citations.append(
            Citation(
                source_uri=citation_source_uri(metadata, ranked.chunk.document_id),
                document_id=ranked.chunk.document_id,
                chunk_index=ranked.chunk.chunk_index,
                content_hash=ranked.chunk.content_hash,
                acl_proof={
                    "tenant_id": ranked.chunk.tenant_id,
                    "collection": ranked.chunk.collection,
                    "acl_hash": str(metadata.get("acl_hash", "")),
                },
            )
        )
    return citations


def citation_source_uri(metadata: Mapping[str, object], document_id: str) -> str:
    for key in ("source_uri", "sourceUri", "source"):
        source_uri = metadata.get(key)
        if isinstance(source_uri, str) and source_uri.strip():
            return source_uri
    return document_id
