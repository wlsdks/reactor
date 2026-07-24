from __future__ import annotations

from reactor.rag.documents import RagChunkCandidate
from reactor.rag.retriever import RetrievalQuery, hybrid_retrieve


def test_employee_rag_search_never_retrieves_executive_salary_document() -> None:
    executive_salary = chunk(
        "executive_salary",
        content="Executive salary bands and compensation plan.",
        acl={"visibility": "private", "groups": ["executive"]},
    )
    employee_handbook = chunk(
        "employee_handbook",
        content="Employee handbook compensation FAQ.",
        acl={"visibility": "tenant"},
    )

    ranked = hybrid_retrieve(
        query=RetrievalQuery(
            tenant_id="tenant_1",
            collection="docs",
            query="executive salary",
            principal_id="employee_1",
            groups=("staff",),
            limit=5,
        ),
        vector_candidates=[executive_salary, employee_handbook],
        keyword_candidates=[executive_salary],
    )

    assert [item.chunk.document_id for item in ranked] == ["employee_handbook"]


def chunk(document_id: str, *, content: str, acl: dict[str, object]) -> RagChunkCandidate:
    return RagChunkCandidate(
        tenant_id="tenant_1",
        collection="docs",
        document_id=document_id,
        chunk_index=0,
        content=content,
        content_hash=f"hash_{document_id}",
        metadata={
            "source_uri": f"s3://docs/{document_id}.md",
            "acl_hash": f"acl_{document_id}",
            "acl": acl,
        },
    )
