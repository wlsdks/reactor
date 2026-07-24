from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy.dialects import postgresql

from reactor.persistence.repositories.rag_postgres import (
    PostgresRagRetriever,
    build_keyword_candidate_query,
    build_vector_candidate_query,
    compile_postgres_sql,
    row_to_candidate,
)
from reactor.rag.retriever import RetrievalQuery


def test_vector_query_filters_tenant_collection_and_acl_before_limit() -> None:
    query = RetrievalQuery(
        tenant_id="tenant_1",
        collection="docs",
        query="reactor",
        principal_id="user_1",
        groups=("engineering",),
        limit=7,
    )

    compiled = build_vector_candidate_query(query, [0.1] * 1536).compile(
        dialect=postgresql.dialect()
    )
    sql = str(compiled)

    assert "rag_chunks.tenant_id =" in sql
    assert "rag_chunks.collection =" in sql
    assert "rag_documents.tenant_id =" in sql
    assert "rag_documents.collection =" in sql
    assert "CAST(rag_documents.acl AS JSONB)" in sql
    assert "<=>" in sql
    assert "LIMIT" in sql
    assert compiled.params["tenant_id_1"] == "tenant_1"
    assert compiled.params["collection_1"] == "docs"
    assert 7 in compiled.params.values()
    assert sql.index("WHERE") < sql.index("LIMIT")


def test_vector_query_allows_tenant_visible_documents_after_tenant_filter() -> None:
    query = RetrievalQuery(
        tenant_id="tenant_1",
        collection="docs",
        query="reactor",
        principal_id="user_1",
        limit=7,
    )

    compiled = build_vector_candidate_query(query, [0.1] * 1536).compile(
        dialect=postgresql.dialect()
    )
    sql = str(compiled)

    assert "rag_documents.tenant_id =" in sql
    assert "CAST(rag_documents.acl AS JSONB)" in sql
    assert "visibility" in compiled.params.values()
    assert "tenant" in compiled.params.values()


def test_vector_query_allows_private_documents_only_for_authenticated_groups() -> None:
    query = RetrievalQuery(
        tenant_id="tenant_1",
        collection="docs",
        query="executive salary",
        principal_id="employee_1",
        groups=("engineering", "executive"),
        limit=7,
    )

    compiled = build_vector_candidate_query(query, [0.1] * 1536).compile(
        dialect=postgresql.dialect()
    )
    sql = str(compiled)

    assert "CAST(rag_documents.acl AS JSONB)" in sql
    assert "groups" in compiled.params.values()
    assert "engineering" in compiled.params.values()
    assert "executive" in compiled.params.values()
    assert "employee_1" in compiled.params.values()
    assert sql.index("WHERE") < sql.index("LIMIT")


def test_vector_query_requires_private_visibility_for_user_or_group_acl() -> None:
    query = RetrievalQuery(
        tenant_id="tenant_1",
        collection="docs",
        query="executive salary",
        principal_id="employee_1",
        groups=("executive",),
        limit=7,
    )

    compiled = build_vector_candidate_query(query, [0.1] * 1536).compile(
        dialect=postgresql.dialect()
    )
    sql = str(compiled)

    assert "users" in compiled.params.values()
    assert "groups" in compiled.params.values()
    assert "private" in compiled.params.values()
    assert sql.index("WHERE") < sql.index("LIMIT")


def test_vector_query_requires_array_acl_subjects_before_private_match() -> None:
    query = RetrievalQuery(
        tenant_id="tenant_1",
        collection="docs",
        query="executive salary",
        principal_id="employee_1",
        groups=("executive",),
        limit=7,
    )

    compiled = build_vector_candidate_query(query, [0.1] * 1536).compile(
        dialect=postgresql.dialect()
    )
    sql = str(compiled)

    assert "jsonb_typeof" in sql
    assert "users" in compiled.params.values()
    assert "groups" in compiled.params.values()
    assert "array" in compiled.params.values()
    assert sql.index("jsonb_typeof") < sql.index("LIMIT")


def test_keyword_query_uses_postgres_full_text_search_with_acl_filter() -> None:
    query = RetrievalQuery(
        tenant_id="tenant_1",
        collection="docs",
        query="reactor safety",
        principal_id="user_1",
        limit=3,
    )

    compiled = build_keyword_candidate_query(query).compile(dialect=postgresql.dialect())
    sql = str(compiled)

    assert "to_tsvector(" in sql
    assert "plainto_tsquery(" in sql
    assert "@@" in sql
    assert "CAST(rag_documents.acl AS JSONB)" in sql
    assert "LIMIT" in sql
    assert compiled.params["plainto_tsquery_1"] == "reactor safety"
    assert 3 in compiled.params.values()


async def test_retriever_executes_vector_and_keyword_queries_then_merges_results() -> None:
    query = RetrievalQuery(
        tenant_id="tenant_1",
        collection="docs",
        query="reactor safety",
        principal_id="user_1",
        limit=3,
    )
    session = FakeSession(
        results=[
            [
                candidate_row(
                    document_id="doc_a",
                    chunk_index=0,
                    content="vector hit",
                    source_uri="https://example.test/vector",
                ),
                candidate_row(document_id="doc_b", chunk_index=0, content="vector only"),
            ],
            [
                candidate_row(
                    document_id="doc_a",
                    chunk_index=0,
                    content="keyword hit",
                    source_uri="https://example.test/vector",
                ),
                candidate_row(document_id="doc_c", chunk_index=0, content="keyword only"),
            ],
        ]
    )

    ranked = await PostgresRagRetriever(FakeSessionFactory(session)).retrieve(
        query,
        [0.1] * 1536,
    )

    candidate_statements = [
        statement for statement in session.statements if "set_config" not in str(statement)
    ]
    assert len(candidate_statements) == 2
    assert ranked[0].chunk.document_id == "doc_a"
    assert ranked[0].vector_rank == 1
    assert ranked[0].keyword_rank == 1
    assert ranked[0].chunk.metadata["source_uri"] == "https://example.test/vector"
    assert [item.chunk.document_id for item in ranked] == ["doc_a", "doc_b", "doc_c"]


async def test_retriever_sets_postgres_rls_context_from_trusted_query_identity() -> None:
    query = RetrievalQuery(
        tenant_id="tenant_1",
        collection="docs",
        query="executive salary",
        principal_id="employee_1",
        groups=("engineering", "finance"),
        limit=3,
    )
    session = FakeSession(results=[[], []])

    await PostgresRagRetriever(FakeSessionFactory(session)).retrieve(query, [0.1] * 1536)

    rls_statements = [
        compile_postgres_sql(statement, literal_binds=True)
        for statement in session.statements
        if "set_config" in compile_postgres_sql(statement, literal_binds=True)
    ]
    assert len(rls_statements) == 3
    assert any(
        "reactor.tenant_id" in statement and "tenant_1" in statement for statement in rls_statements
    )
    assert any(
        "reactor.user_id" in statement and "employee_1" in statement for statement in rls_statements
    )
    assert any(
        "reactor.user_groups" in statement and '["engineering","finance"]' in statement
        for statement in rls_statements
    )


def test_row_to_candidate_preserves_acl_metadata_and_source_uri() -> None:
    candidate = row_to_candidate(
        candidate_row(
            document_id="doc_a",
            chunk_index=2,
            content="chunk body",
            metadata={"acl": {"visibility": "public"}, "section": "runtime"},
            source_uri="s3://docs/reactor.md",
        ),
        tenant_id="tenant_1",
        collection="docs",
    )

    assert candidate.tenant_id == "tenant_1"
    assert candidate.collection == "docs"
    assert candidate.document_id == "doc_a"
    assert candidate.chunk_index == 2
    assert candidate.acl()["visibility"] == "public"
    assert candidate.metadata["section"] == "runtime"
    assert candidate.metadata["source_uri"] == "s3://docs/reactor.md"


def test_row_to_candidate_uses_canonical_document_acl_when_chunk_metadata_omits_acl() -> None:
    candidate = row_to_candidate(
        candidate_row(
            document_id="doc_private",
            chunk_index=0,
            content="Executive salary private note.",
            metadata={"section": "compensation"},
            source_uri="s3://docs/executive-salary.md",
            document_acl={"visibility": "private", "groups": ["executive"]},
        ),
        tenant_id="tenant_1",
        collection="docs",
    )

    assert candidate.acl() == {"visibility": "private", "groups": ["executive"]}
    assert candidate.metadata["acl_hash"]


class FakeMappingResult:
    def __init__(self, rows: list[Mapping[str, Any]]) -> None:
        self._rows = rows

    def all(self) -> list[Mapping[str, Any]]:
        return self._rows


class FakeResult:
    def __init__(self, rows: list[Mapping[str, Any]]) -> None:
        self._rows = rows

    def mappings(self) -> FakeMappingResult:
        return FakeMappingResult(self._rows)


class FakeSession:
    def __init__(self, results: list[list[Mapping[str, Any]]]) -> None:
        self._results = iter(results)
        self.statements: list[Any] = []

    async def execute(self, statement: Any) -> FakeResult:
        self.statements.append(statement)
        if "set_config" in str(statement):
            return FakeResult([])
        return FakeResult(next(self._results))

    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        return None


class FakeSessionFactory:
    def __init__(self, session: FakeSession) -> None:
        self._session = session

    def __call__(self) -> FakeSession:
        return self._session


def candidate_row(
    *,
    document_id: str,
    chunk_index: int,
    content: str,
    metadata: Mapping[str, Any] | None = None,
    source_uri: str = "https://example.test/source",
    document_acl: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    return {
        "chunk_id": f"{document_id}_{chunk_index}",
        "document_id": document_id,
        "chunk_index": chunk_index,
        "content": content,
        "content_hash": f"hash_{document_id}_{chunk_index}",
        "metadata": metadata or {"acl": {"visibility": "public"}},
        "document_acl": document_acl,
        "source_uri": source_uri,
        "rank": 1,
    }
