from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from hashlib import sha256
from typing import Any, Protocol
from typing import cast as typing_cast

from sqlalchemy import Select, and_, false, func, literal, or_, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import cast as sql_cast
from sqlalchemy.sql.elements import ColumnElement

from reactor.persistence.models import RagChunk, RagDocument, RagSource
from reactor.rag.documents import RagChunkCandidate
from reactor.rag.retriever import RankedChunk, RetrievalQuery, reciprocal_rank_fusion


class _MappingResult(Protocol):
    def all(self) -> Sequence[Mapping[str, Any]]: ...


class _ExecutableResult(Protocol):
    def mappings(self) -> _MappingResult: ...


class _ExecutableSession(Protocol):
    async def execute(self, statement: Any) -> _ExecutableResult: ...


class _SessionContext(Protocol):
    async def __aenter__(self) -> _ExecutableSession: ...

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> None: ...


class _SessionFactory(Protocol):
    def __call__(self) -> _SessionContext: ...


def build_vector_candidate_query(
    query: RetrievalQuery,
    embedding: Sequence[float],
) -> Select[tuple[str, str, int, str, str, dict[str, object], dict[str, object], str, int]]:
    base = base_candidate_query(query)
    distance = RagChunk.embedding.op("<=>")(list(embedding))
    return (
        base.add_columns(func.row_number().over(order_by=distance.asc()).label("rank"))
        .where(RagChunk.embedding.is_not(None))
        .order_by(distance.asc())
        .limit(query.limit)
    )


def build_keyword_candidate_query(
    query: RetrievalQuery,
) -> Select[tuple[str, str, int, str, str, dict[str, object], dict[str, object], str, int]]:
    base = base_candidate_query(query)
    config = literal("simple").cast(postgresql.REGCONFIG)
    document = func.to_tsvector(config, RagChunk.content)
    ts_query = func.plainto_tsquery(config, query.query)
    rank = func.ts_rank_cd(document, ts_query)
    return (
        base.add_columns(func.row_number().over(order_by=rank.desc()).label("rank"))
        .where(document.op("@@")(ts_query))
        .order_by(rank.desc())
        .limit(query.limit)
    )


def base_candidate_query(
    query: RetrievalQuery,
) -> Select[tuple[str, str, int, str, str, dict[str, object], dict[str, object], str]]:
    query.validate()
    acl = sql_cast(RagDocument.acl, JSONB)
    metadata = sql_cast(RagChunk.chunk_metadata, JSONB)
    return (
        select(
            RagChunk.id.label("chunk_id"),
            RagChunk.document_id,
            RagChunk.chunk_index,
            RagChunk.content,
            RagChunk.content_hash,
            metadata.label("metadata"),
            acl.label("document_acl"),
            RagSource.source_uri,
        )
        .join(RagDocument, RagDocument.id == RagChunk.document_id)
        .join(RagSource, RagSource.id == RagDocument.source_id)
        .where(
            RagChunk.tenant_id == query.tenant_id,
            RagChunk.collection == query.collection,
            RagDocument.tenant_id == query.tenant_id,
            RagDocument.collection == query.collection,
            acl_predicate(acl, query),
        )
    )


def acl_predicate(acl: Any, query: RetrievalQuery) -> ColumnElement[bool]:
    users = acl["users"]
    groups = acl["groups"]
    users_is_array = func.jsonb_typeof(users) == "array"
    groups_is_array = func.jsonb_typeof(groups) == "array"
    group_predicates: list[ColumnElement[bool]] = [
        groups.op("?")(group) for group in query.groups if group.strip()
    ]
    private_acl_match = or_(
        and_(users_is_array, users.op("?")(query.principal_id)),
        and_(groups_is_array, literal(bool(group_predicates)), or_(*group_predicates))
        if group_predicates
        else false(),
    )
    return or_(
        acl["visibility"].astext == "public",
        acl["visibility"].astext == "tenant",
        and_(acl["visibility"].astext == "private", private_acl_match),
    )


def compile_postgres_sql(statement: Any, *, literal_binds: bool = False) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": literal_binds},
        )
    )


class PostgresRagRetriever:
    def __init__(self, session_factory: _SessionFactory) -> None:
        self._session_factory = session_factory

    async def retrieve(
        self,
        query: RetrievalQuery,
        embedding: Sequence[float],
    ) -> list[RankedChunk]:
        query.validate()
        async with self._session_factory() as session:
            await set_rag_rls_context(session, query)
            vector_rows = await self._execute_candidate_query(
                session,
                build_vector_candidate_query(query, embedding),
                query,
            )
            keyword_rows = await self._execute_candidate_query(
                session,
                build_keyword_candidate_query(query),
                query,
            )

        return reciprocal_rank_fusion(
            vector_ranked=vector_rows,
            keyword_ranked=keyword_rows,
            limit=query.limit,
        )

    async def _execute_candidate_query(
        self,
        session: _ExecutableSession,
        statement: Any,
        query: RetrievalQuery,
    ) -> list[RagChunkCandidate]:
        result = await session.execute(statement)
        return rows_to_candidates(
            result.mappings().all(),
            tenant_id=query.tenant_id,
            collection=query.collection,
        )


def rows_to_candidates(
    rows: Sequence[Mapping[str, Any]],
    *,
    tenant_id: str,
    collection: str,
) -> list[RagChunkCandidate]:
    return [row_to_candidate(row, tenant_id=tenant_id, collection=collection) for row in rows]


async def set_rag_rls_context(session: Any, query: RetrievalQuery) -> None:
    await set_rag_rls_context_values(
        session,
        tenant_id=query.tenant_id,
        user_id=query.principal_id,
        groups=query.groups,
    )


async def set_rag_rls_context_values(
    session: Any,
    *,
    tenant_id: str,
    user_id: str,
    groups: Sequence[str] = (),
) -> None:
    groups = json.dumps(
        [group.strip() for group in groups if group.strip()],
        separators=(",", ":"),
    )
    await session.execute(select(func.set_config("reactor.tenant_id", tenant_id, True)))
    await session.execute(select(func.set_config("reactor.user_id", user_id, True)))
    await session.execute(select(func.set_config("reactor.user_groups", groups, True)))


def row_to_candidate(
    row: Mapping[str, Any],
    *,
    tenant_id: str,
    collection: str,
) -> RagChunkCandidate:
    metadata = metadata_from_row(row)
    source_uri = row.get("source_uri")
    if isinstance(source_uri, str) and source_uri:
        metadata["source_uri"] = source_uri

    candidate = RagChunkCandidate(
        tenant_id=tenant_id,
        collection=collection,
        document_id=str(row["document_id"]),
        chunk_index=int(row["chunk_index"]),
        content=str(row["content"]),
        content_hash=str(row["content_hash"]),
        metadata=metadata,
    )
    candidate.validate()
    return candidate


def metadata_from_row(row: Mapping[str, Any]) -> dict[str, Any]:
    metadata = row.get("metadata")
    result = dict(typing_cast(Mapping[str, Any], metadata)) if isinstance(metadata, Mapping) else {}
    document_acl = row.get("document_acl")
    if isinstance(document_acl, Mapping):
        acl = dict(typing_cast(Mapping[str, Any], document_acl))
        result["acl"] = acl
        result.setdefault("acl_hash", stable_acl_hash(acl))
    return result


def stable_acl_hash(acl: Mapping[str, Any]) -> str:
    payload = json.dumps(acl, sort_keys=True, separators=(",", ":"), default=str)
    return f"sha256:{sha256(payload.encode('utf-8')).hexdigest()}"
