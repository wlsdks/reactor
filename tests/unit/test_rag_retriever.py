from __future__ import annotations

from typing import Final, cast

from reactor.rag.citations import build_citations
from reactor.rag.documents import RagChunkCandidate
from reactor.rag.retriever import RetrievalQuery, hybrid_retrieve, reciprocal_rank_fusion

DEFAULT_ACL: Final = {"visibility": "public"}


def test_hybrid_retrieval_filters_tenant_collection_and_acl_before_ranking() -> None:
    visible = chunk(
        "doc_visible",
        acl={"users": ["user_1"], "visibility": "private"},
    )
    wrong_tenant = chunk("doc_wrong_tenant", tenant_id="tenant_2", acl={"users": ["user_1"]})
    wrong_collection = chunk("doc_wrong_collection", collection="other", acl={"users": ["user_1"]})
    denied = chunk("doc_denied", acl={"users": ["user_2"], "visibility": "private"})
    query = RetrievalQuery(
        tenant_id="tenant_1",
        collection="docs",
        query="reactor",
        principal_id="user_1",
        limit=5,
    )

    ranked = hybrid_retrieve(
        query=query,
        vector_candidates=[wrong_tenant, visible, denied],
        keyword_candidates=[wrong_collection, denied],
    )

    assert [item.chunk.document_id for item in ranked] == ["doc_visible"]


def test_hybrid_retrieval_allows_tenant_visible_chunks_after_tenant_filter() -> None:
    tenant_visible = chunk("doc_tenant", acl={"visibility": "tenant"})
    wrong_tenant = chunk(
        "doc_wrong_tenant",
        tenant_id="tenant_2",
        acl={"visibility": "tenant"},
    )
    query = RetrievalQuery(
        tenant_id="tenant_1",
        collection="docs",
        query="reactor",
        principal_id="user_1",
        limit=5,
    )

    ranked = hybrid_retrieve(
        query=query,
        vector_candidates=[wrong_tenant, tenant_visible],
        keyword_candidates=[],
    )

    assert [item.chunk.document_id for item in ranked] == ["doc_tenant"]


def test_hybrid_retrieval_denies_chunks_without_explicit_acl_visibility() -> None:
    missing_acl = chunk("doc_missing_acl", acl={})
    missing_visibility = chunk("doc_missing_visibility", acl={"groups": ["engineering"]})
    malformed_visibility = chunk("doc_malformed_visibility", acl={"visibility": "confidential"})
    visible = chunk("doc_visible", acl={"visibility": "tenant"})
    query = RetrievalQuery(
        tenant_id="tenant_1",
        collection="docs",
        query="executive salary",
        principal_id="employee_1",
        groups=("engineering",),
        limit=5,
    )

    ranked = hybrid_retrieve(
        query=query,
        vector_candidates=[missing_acl, missing_visibility, malformed_visibility, visible],
        keyword_candidates=[],
    )

    assert [item.chunk.document_id for item in ranked] == ["doc_visible"]


def test_hybrid_retrieval_denies_malformed_private_acl_subjects() -> None:
    malformed_users = chunk(
        "doc_malformed_users",
        acl={"visibility": "private", "users": "employee_1"},
    )
    malformed_groups = chunk(
        "doc_malformed_groups",
        acl={"visibility": "private", "groups": "executive"},
    )
    visible = chunk("doc_visible", acl={"visibility": "tenant"})
    query = RetrievalQuery(
        tenant_id="tenant_1",
        collection="docs",
        query="executive salary",
        principal_id="employee_1",
        groups=("executive",),
        limit=5,
    )

    ranked = hybrid_retrieve(
        query=query,
        vector_candidates=[malformed_users, malformed_groups, visible],
        keyword_candidates=[],
    )

    assert [item.chunk.document_id for item in ranked] == ["doc_visible"]


def test_hybrid_retrieval_never_expands_malformed_acl_subjects() -> None:
    malformed_user_string = chunk(
        "doc_malformed_user_string",
        acl={"visibility": "private", "users": "employee_1"},
    )
    malformed_group_member = chunk(
        "doc_malformed_group_member",
        acl={"visibility": "private", "groups": [123]},
    )
    query = RetrievalQuery(
        tenant_id="tenant_1",
        collection="docs",
        query="executive salary",
        principal_id="e",
        groups=("123",),
        limit=5,
    )

    ranked = hybrid_retrieve(
        query=query,
        vector_candidates=[malformed_user_string, malformed_group_member],
        keyword_candidates=[],
    )

    assert ranked == []


def test_rrf_merges_vector_and_keyword_rank_for_same_chunk() -> None:
    both = chunk("doc_both")
    vector_only = chunk("doc_vector")
    keyword_only = chunk("doc_keyword")

    ranked = reciprocal_rank_fusion(
        vector_ranked=[both, vector_only],
        keyword_ranked=[keyword_only, both],
        limit=3,
    )

    assert ranked[0].chunk.document_id == "doc_both"
    assert ranked[0].vector_rank == 1
    assert ranked[0].keyword_rank == 2
    assert {item.chunk.document_id for item in ranked} == {"doc_both", "doc_vector", "doc_keyword"}


def test_citations_preserve_source_chunk_hash_and_acl_proof() -> None:
    ranked = reciprocal_rank_fusion(vector_ranked=[chunk("doc_1")], keyword_ranked=[], limit=1)

    citations = build_citations(ranked)

    assert len(citations) == 1
    assert citations[0].source_uri == "s3://bucket/doc_1.md"
    assert citations[0].document_id == "doc_1"
    assert citations[0].chunk_index == 0
    assert citations[0].content_hash == "hash_doc_1"
    assert citations[0].acl_proof == {
        "tenant_id": "tenant_1",
        "collection": "docs",
        "acl_hash": "acl_doc_1",
    }


def test_citations_fall_back_to_document_id_when_source_uri_is_missing() -> None:
    missing_source = chunk("doc_missing_source")
    blank_source = chunk("doc_blank_source")
    none_source = chunk("doc_none_source")
    cast(dict[str, object], missing_source.metadata).pop("source_uri")
    cast(dict[str, object], blank_source.metadata)["source_uri"] = " "
    cast(dict[str, object], none_source.metadata)["source_uri"] = None
    ranked = reciprocal_rank_fusion(
        vector_ranked=[missing_source, blank_source, none_source],
        keyword_ranked=[],
        limit=3,
    )

    citations = build_citations(ranked)

    assert {citation.source_uri for citation in citations} == {
        "doc_missing_source",
        "doc_blank_source",
        "doc_none_source",
    }


def chunk(
    document_id: str,
    *,
    tenant_id: str = "tenant_1",
    collection: str = "docs",
    acl: dict[str, object] | None = None,
) -> RagChunkCandidate:
    actual_acl = DEFAULT_ACL if acl is None else acl
    return RagChunkCandidate(
        tenant_id=tenant_id,
        collection=collection,
        document_id=document_id,
        chunk_index=0,
        content=f"content for {document_id}",
        content_hash=f"hash_{document_id}",
        metadata={
            "source_uri": f"s3://bucket/{document_id}.md",
            "acl_hash": f"acl_{document_id}",
            "acl": actual_acl,
        },
    )
