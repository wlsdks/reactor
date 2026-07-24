from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from reactor.rag.documents import RagChunkCandidate


@dataclass(frozen=True)
class RetrievalQuery:
    tenant_id: str
    collection: str
    query: str
    principal_id: str
    groups: tuple[str, ...] = ()
    limit: int = 5

    def validate(self) -> None:
        for field_name, value in (
            ("tenant_id", self.tenant_id),
            ("collection", self.collection),
            ("query", self.query),
            ("principal_id", self.principal_id),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} is required")
        if self.limit <= 0:
            raise ValueError("limit must be positive")


@dataclass(frozen=True)
class RankedChunk:
    chunk: RagChunkCandidate
    score: float
    vector_rank: int | None = None
    keyword_rank: int | None = None


def filter_candidates_before_ranking(
    query: RetrievalQuery,
    candidates: Iterable[RagChunkCandidate],
) -> list[RagChunkCandidate]:
    query.validate()
    filtered: list[RagChunkCandidate] = []
    for candidate in candidates:
        candidate.validate()
        if candidate.tenant_id != query.tenant_id:
            continue
        if candidate.collection != query.collection:
            continue
        if not principal_can_read(candidate.acl(), query.principal_id, query.groups):
            continue
        filtered.append(candidate)
    return filtered


def principal_can_read(
    acl: Mapping[str, Any],
    principal_id: str,
    groups: Sequence[str] = (),
) -> bool:
    visibility_value = acl.get("visibility")
    if not isinstance(visibility_value, str):
        return False
    visibility = visibility_value.strip()
    if visibility in {"public", "tenant"}:
        return True
    if visibility != "private":
        return False
    allowed_users = acl_subjects(acl.get("users", ()))
    allowed_groups = acl_subjects(acl.get("groups", ()))
    if allowed_users is None or allowed_groups is None:
        return False
    if principal_id in allowed_users:
        return True
    return any(group in allowed_groups for group in groups)


def acl_subjects(value: Any) -> tuple[str, ...] | None:
    if value is None:
        return ()
    if isinstance(value, str) or not isinstance(value, Sequence):
        return None
    candidate_subjects = cast(Sequence[object], value)
    subjects: list[str] = []
    for item in candidate_subjects:
        if not isinstance(item, str) or not item.strip():
            return None
        subjects.append(item)
    return tuple(subjects)


def reciprocal_rank_fusion(
    *,
    vector_ranked: Sequence[RagChunkCandidate],
    keyword_ranked: Sequence[RagChunkCandidate],
    limit: int,
    rank_constant: int = 60,
) -> list[RankedChunk]:
    scores: dict[tuple[str, int], float] = {}
    chunks: dict[tuple[str, int], RagChunkCandidate] = {}
    vector_ranks: dict[tuple[str, int], int] = {}
    keyword_ranks: dict[tuple[str, int], int] = {}

    for rank, chunk in enumerate(vector_ranked, start=1):
        key = chunk_key(chunk)
        chunks[key] = chunk
        vector_ranks[key] = rank
        scores[key] = scores.get(key, 0.0) + 1.0 / (rank_constant + rank)
    for rank, chunk in enumerate(keyword_ranked, start=1):
        key = chunk_key(chunk)
        chunks[key] = chunk
        keyword_ranks[key] = rank
        scores[key] = scores.get(key, 0.0) + 1.0 / (rank_constant + rank)

    ranked = [
        RankedChunk(
            chunk=chunks[key],
            score=score,
            vector_rank=vector_ranks.get(key),
            keyword_rank=keyword_ranks.get(key),
        )
        for key, score in scores.items()
    ]
    ranked.sort(key=lambda item: (-item.score, item.chunk.document_id, item.chunk.chunk_index))
    return ranked[:limit]


def hybrid_retrieve(
    *,
    query: RetrievalQuery,
    vector_candidates: Sequence[RagChunkCandidate],
    keyword_candidates: Sequence[RagChunkCandidate],
) -> list[RankedChunk]:
    filtered_vector = filter_candidates_before_ranking(query, vector_candidates)
    filtered_keyword = filter_candidates_before_ranking(query, keyword_candidates)
    return reciprocal_rank_fusion(
        vector_ranked=filtered_vector,
        keyword_ranked=filtered_keyword,
        limit=query.limit,
    )


def chunk_key(chunk: RagChunkCandidate) -> tuple[str, int]:
    return (chunk.document_id, chunk.chunk_index)
