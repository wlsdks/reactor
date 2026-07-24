from __future__ import annotations

from hashlib import sha256
from typing import cast

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from reactor.context.diagnostics import context_manifest_diagnostics
from reactor.context.manifest import CONTEXT_SECTION_ORDER, ContextManifest, ContextSection
from reactor.context.trimming import trim_to_message_pair_boundary

VALID_MEMORY_CHECKSUM = "sha256:" + ("a" * 64)
VALID_RAG_CHECKSUM = "sha256:" + ("b" * 64)


def valid_citation(
    citation_id: str,
    *,
    source_uri: str = "https://docs.example/runbook",
    content_hash: str = "hash_1",
) -> dict[str, object]:
    return {
        "citation_id": citation_id,
        "source_uri": source_uri,
        "content_hash": content_hash,
    }


def test_context_manifest_renders_sections_in_spec_order() -> None:
    manifest = ContextManifest(
        sections=[
            ContextSection("tool_outputs", "tool result"),
            ContextSection("latest_user_request", "user asks"),
            ContextSection("request_system_prompt", "request policy"),
            ContextSection("system_policy", "policy"),
            ContextSection("rag_context", "source"),
        ]
    )

    assert [section.name for section in manifest.ordered_sections()] == [
        "system_policy",
        "request_system_prompt",
        "latest_user_request",
        "rag_context",
        "tool_outputs",
    ]


def test_context_manifest_rejects_unknown_section() -> None:
    with pytest.raises(ValueError, match="unknown context section"):
        ContextManifest(sections=[ContextSection("unknown", "x")]).ordered_sections()


def test_context_manifest_preserves_section_evidence_without_model_visible_acl_markers() -> None:
    manifest = ContextManifest(
        sections=[
            ContextSection(
                "rag_context",
                (
                    "source text\n"
                    "acl_user_36871ea355450eb18ef70c7f22e9872b550d7658053c805fc72de3b14600115c=1\n"
                    "acl_group_180b988a36f655a375c5eadb524e0364aa1acd22c07568c1789235ae54a5514a=1\n"
                    "acl={'visibility': 'private'}"
                ),
                source_type="rag",
                tenant_id="tenant_1",
                tainted=True,
                metadata={
                    "source_uri": "https://docs.example/private",
                    "document_id": "doc_1",
                    "chunk_index": 0,
                    "content_hash": "hash_1",
                    "acl_hash": "acl_1",
                    "citation_id": "doc_1:0",
                },
            )
        ]
    )

    rendered = manifest.render()
    model_visible_content = manifest.sections[0].model_visible_content()
    assert "source text" in rendered
    assert "acl_user_" not in rendered
    assert "acl_group_" not in rendered
    assert "visibility" not in rendered
    assert manifest.as_manifest() == {
        "sections": [
            {
                "name": "rag_context",
                "source_type": "rag",
                "tenant_id": "tenant_1",
                "tainted": True,
                "content_length": len(manifest.sections[0].content),
                "content_checksum": f"sha256:{sha256(model_visible_content.encode()).hexdigest()}",
                "metadata": {
                    "source_uri": "https://docs.example/private",
                    "document_id": "doc_1",
                    "chunk_index": 0,
                    "content_hash": "hash_1",
                    "acl_hash": "acl_1",
                    "citation_id": "doc_1:0",
                },
            }
        ]
    }


def test_context_manifest_redacts_authorization_metadata_from_manifest_entries() -> None:
    manifest = ContextManifest(
        sections=[
            ContextSection(
                "rag_context",
                "private source text",
                source_type="rag",
                tenant_id="tenant_1",
                tainted=True,
                metadata={
                    "source_uri": "https://docs.example/private",
                    "document_id": "doc_private",
                    "chunk_index": 0,
                    "content_hash": "hash_private",
                    "acl_hash": "acl_private",
                    "acl": {"visibility": "private", "groups": ["executive"]},
                    "acl_visibility": "private",
                    "acl_users": ["ceo_1"],
                    "acl_groups": ["executive"],
                    "acl_user_marker": "1",
                    "acl_group_marker": "1",
                    "acl_proof": {
                        "tenant_id": "tenant_1",
                        "collection": "docs",
                        "acl_hash": "acl_private",
                    },
                    "citations": [
                        {
                            "citation_id": "doc_private:0",
                            "source_uri": "https://docs.example/private",
                            "acl_proof": {"tenant_id": "tenant_1", "acl_hash": "acl_private"},
                        }
                    ],
                },
            )
        ]
    )

    sections = cast(list[dict[str, object]], manifest.as_manifest()["sections"])
    metadata = sections[0]["metadata"]

    assert metadata == {
        "source_uri": "https://docs.example/private",
        "document_id": "doc_private",
        "chunk_index": 0,
        "content_hash": "hash_private",
        "acl_hash": "acl_private",
        "citations": [
            {
                "citation_id": "doc_private:0",
                "source_uri": "https://docs.example/private",
            }
        ],
    }


def test_context_manifest_diagnostics_flags_raw_acl_and_missing_checksums() -> None:
    result = context_manifest_diagnostics(
        {
            "sections": [
                {
                    "name": "rag_context",
                    "metadata": {
                        "ragGroundingPolicy": {
                            "citationTracking": "required",
                            "uncitedChunksTracked": True,
                            "aclEvidence": "acl_hash_only",
                            "rawAclMetadataVisible": False,
                        },
                        "citation_count": 1,
                        "citations": [valid_citation("doc_1:0")],
                        "acl_user_marker": "1",
                    },
                }
            ]
        }
    )

    assert result["ok"] is False
    assert result["status"] == "failed"
    assert result["rawAclMetadataVisible"] is True
    assert result["findings"] == [
        {
            "code": "raw_acl_metadata",
            "section": "rag_context",
            "path": "metadata.acl_user_marker",
        },
        {"code": "missing_content_checksum", "section": "rag_context"},
    ]


def test_context_manifest_diagnostics_requires_memory_and_rag_policies() -> None:
    result = context_manifest_diagnostics(
        {
            "sections": [
                {
                    "name": "session_memory",
                    "content_checksum": VALID_MEMORY_CHECKSUM,
                    "metadata": {"memory_count": 1},
                },
                {
                    "name": "rag_context",
                    "content_checksum": VALID_RAG_CHECKSUM,
                    "metadata": {"citation_count": 0},
                },
            ]
        }
    )

    assert result["ok"] is False
    assert result["status"] == "failed"
    assert result["findings"] == [
        {
            "code": "missing_memory_admission_policy",
            "section": "session_memory",
            "path": "metadata.memoryAdmissionPolicy",
        },
        {
            "code": "missing_rag_grounding_policy",
            "section": "rag_context",
            "path": "metadata.ragGroundingPolicy",
        },
    ]


def test_context_manifest_diagnostics_reports_memory_status_counts() -> None:
    result = context_manifest_diagnostics(
        {
            "sections": [
                {
                    "name": "session_memory",
                    "content_checksum": VALID_MEMORY_CHECKSUM,
                    "metadata": {
                        "memoryAdmissionPolicy": {
                            "activeOnly": True,
                            "missingStatusExcluded": True,
                            "tombstonedExcluded": True,
                            "supersededExcluded": True,
                        },
                        "memory_count": 2,
                        "skipped_memory_count": 3,
                        "skipped_status_counts": {
                            "tombstoned": 1,
                            "missing": 2,
                        },
                        "status_counts": {
                            "active": 2,
                            "tombstoned": 1,
                            "missing": 2,
                        },
                    },
                }
            ]
        }
    )

    assert result["ok"] is True
    assert result["memoryCount"] == 2
    assert result["skippedMemoryCount"] == 3
    assert result["skippedMemoryStatusCounts"] == {
        "tombstoned": 1,
        "missing": 2,
    }
    assert result["memoryStatusCounts"] == {
        "active": 2,
        "tombstoned": 1,
        "missing": 2,
    }


def test_context_manifest_diagnostics_rejects_inconsistent_memory_status_counts() -> None:
    result = context_manifest_diagnostics(
        {
            "sections": [
                {
                    "name": "session_memory",
                    "content_checksum": VALID_MEMORY_CHECKSUM,
                    "metadata": {
                        "memoryAdmissionPolicy": {
                            "activeOnly": True,
                            "missingStatusExcluded": True,
                            "tombstonedExcluded": True,
                            "supersededExcluded": True,
                        },
                        "memory_count": 1,
                        "skipped_memory_count": 2,
                        "status_counts": {"active": 1},
                    },
                }
            ]
        }
    )

    assert result["ok"] is False
    findings = cast(list[dict[str, object]], result["findings"])
    assert {
        "code": "memory_status_count_mismatch",
        "section": "session_memory",
        "path": "metadata.status_counts",
        "memoryCount": 1,
        "skippedMemoryCount": 2,
        "statusCountTotal": 1,
    } in findings


def test_context_manifest_diagnostics_rejects_unknown_memory_status_counts() -> None:
    result = context_manifest_diagnostics(
        {
            "sections": [
                {
                    "name": "session_memory",
                    "content_checksum": VALID_MEMORY_CHECKSUM,
                    "metadata": {
                        "memoryAdmissionPolicy": {
                            "activeOnly": True,
                            "missingStatusExcluded": True,
                            "tombstonedExcluded": True,
                            "supersededExcluded": True,
                        },
                        "memory_count": 1,
                        "skipped_memory_count": 1,
                        "status_counts": {"active": 1, "deleted": 1},
                    },
                }
            ]
        }
    )

    assert result["ok"] is False
    findings = cast(list[dict[str, object]], result["findings"])
    assert {
        "code": "unknown_memory_status_count",
        "section": "session_memory",
        "path": "metadata.status_counts.deleted",
        "status": "deleted",
    } in findings


def test_context_manifest_diagnostics_rejects_duplicate_sections() -> None:
    result = context_manifest_diagnostics(
        {
            "sections": [
                {
                    "name": "rag_context",
                    "content_checksum": VALID_RAG_CHECKSUM,
                    "metadata": {
                        "ragGroundingPolicy": {
                            "citationTracking": "required",
                            "uncitedChunksTracked": True,
                            "aclEvidence": "acl_hash_only",
                            "rawAclMetadataVisible": False,
                        },
                        "citation_count": 1,
                        "chunk_count": 1,
                        "cited_chunk_count": 1,
                        "uncited_chunk_count": 0,
                        "citations": [valid_citation("doc_1:0")],
                    },
                },
                {
                    "name": "rag_context",
                    "content_checksum": VALID_RAG_CHECKSUM,
                    "metadata": {
                        "ragGroundingPolicy": {
                            "citationTracking": "required",
                            "uncitedChunksTracked": True,
                            "aclEvidence": "acl_hash_only",
                            "rawAclMetadataVisible": False,
                        },
                        "citation_count": 1,
                        "chunk_count": 1,
                        "cited_chunk_count": 1,
                        "uncited_chunk_count": 0,
                        "citations": [valid_citation("doc_2:0", content_hash="hash_2")],
                    },
                },
            ]
        }
    )

    assert result["ok"] is False
    assert result["status"] == "failed"
    assert result["findings"] == [
        {
            "code": "duplicate_context_section",
            "section": "rag_context",
            "path": "sections[1].name",
        }
    ]


def test_context_manifest_diagnostics_rejects_unknown_sections() -> None:
    result = context_manifest_diagnostics(
        {
            "sections": [
                {
                    "name": "scratchpad",
                    "content_checksum": VALID_RAG_CHECKSUM,
                    "metadata": {"source": "external_report"},
                }
            ]
        }
    )

    assert result["ok"] is False
    assert result["status"] == "failed"
    assert result["findings"] == [
        {
            "code": "unknown_context_section",
            "section": "scratchpad",
            "path": "sections[0].name",
        }
    ]


def test_context_manifest_diagnostics_rejects_malformed_content_checksum() -> None:
    result = context_manifest_diagnostics(
        {
            "sections": [
                {
                    "name": "rag_context",
                    "content_checksum": "sha256:rag",
                    "metadata": {
                        "ragGroundingPolicy": {
                            "citationTracking": "required",
                            "uncitedChunksTracked": True,
                            "aclEvidence": "acl_hash_only",
                            "rawAclMetadataVisible": False,
                        },
                        "citation_count": 1,
                        "chunk_count": 1,
                        "cited_chunk_count": 1,
                        "uncited_chunk_count": 0,
                        "citations": [valid_citation("doc_1:0")],
                    },
                }
            ]
        }
    )

    assert result["ok"] is False
    assert result["status"] == "failed"
    assert result["findings"] == [
        {
            "code": "invalid_content_checksum",
            "section": "rag_context",
            "path": "content_checksum",
            "expected": "sha256:<64-hex>",
            "actual": "sha256:rag",
        }
    ]


def test_context_manifest_diagnostics_rejects_weakened_manifest_policies() -> None:
    result = context_manifest_diagnostics(
        {
            "sections": [
                {
                    "name": "session_memory",
                    "content_checksum": VALID_MEMORY_CHECKSUM,
                    "metadata": {
                        "memoryAdmissionPolicy": {
                            "activeOnly": False,
                            "missingStatusExcluded": True,
                            "tombstonedExcluded": True,
                            "supersededExcluded": True,
                        }
                    },
                },
                {
                    "name": "rag_context",
                    "content_checksum": VALID_RAG_CHECKSUM,
                    "metadata": {
                        "ragGroundingPolicy": {
                            "citationTracking": "optional",
                            "uncitedChunksTracked": True,
                            "aclEvidence": "raw_acl",
                            "rawAclMetadataVisible": False,
                        },
                        "citation_count": 1,
                        "chunk_count": 1,
                        "cited_chunk_count": 1,
                        "uncited_chunk_count": 0,
                        "citations": [valid_citation("doc_1:0")],
                    },
                },
            ]
        }
    )

    assert result["ok"] is False
    assert result["status"] == "failed"
    assert result["findings"] == [
        {
            "code": "invalid_memory_admission_policy",
            "section": "session_memory",
            "path": "metadata.memoryAdmissionPolicy.activeOnly",
            "expected": True,
            "actual": False,
        },
        {
            "code": "invalid_rag_grounding_policy",
            "section": "rag_context",
            "path": "metadata.ragGroundingPolicy.citationTracking",
            "expected": "required",
            "actual": "optional",
        },
        {
            "code": "invalid_rag_grounding_policy",
            "section": "rag_context",
            "path": "metadata.ragGroundingPolicy.aclEvidence",
            "expected": "acl_hash_only",
            "actual": "raw_acl",
        },
    ]


def test_context_manifest_diagnostics_reports_rag_grounding_counts() -> None:
    result = context_manifest_diagnostics(
        {
            "sections": [
                {
                    "name": "rag_context",
                    "content_checksum": VALID_RAG_CHECKSUM,
                    "metadata": {
                        "ragGroundingPolicy": {
                            "citationTracking": "required",
                            "uncitedChunksTracked": True,
                            "aclEvidence": "acl_hash_only",
                            "rawAclMetadataVisible": False,
                        },
                        "citation_count": 2,
                        "chunk_count": 3,
                        "cited_chunk_count": 2,
                        "uncited_chunk_count": 1,
                        "citations": [
                            valid_citation("doc_1:0"),
                            valid_citation("doc_2:1", content_hash="hash_2"),
                        ],
                    },
                }
            ]
        }
    )

    assert result["ok"] is True
    assert result["citationCount"] == 2
    assert result["chunkCount"] == 3
    assert result["citedChunkCount"] == 2
    assert result["uncitedChunkCount"] == 1


def test_context_manifest_diagnostics_requires_citation_evidence_for_positive_count() -> None:
    result = context_manifest_diagnostics(
        {
            "sections": [
                {
                    "name": "rag_context",
                    "content_checksum": VALID_RAG_CHECKSUM,
                    "metadata": {
                        "ragGroundingPolicy": {
                            "citationTracking": "required",
                            "uncitedChunksTracked": True,
                            "aclEvidence": "acl_hash_only",
                            "rawAclMetadataVisible": False,
                        },
                        "citation_count": 1,
                        "chunk_count": 1,
                        "cited_chunk_count": 1,
                        "uncited_chunk_count": 0,
                    },
                }
            ]
        }
    )

    assert result["ok"] is False
    assert result["status"] == "failed"
    assert result["findings"] == [
        {
            "code": "missing_rag_citation_evidence",
            "section": "rag_context",
            "path": "metadata.citations",
            "citationCount": 1,
        }
    ]


def test_context_manifest_diagnostics_rejects_rag_citation_count_mismatch() -> None:
    result = context_manifest_diagnostics(
        {
            "sections": [
                {
                    "name": "rag_context",
                    "content_checksum": VALID_RAG_CHECKSUM,
                    "metadata": {
                        "ragGroundingPolicy": {
                            "citationTracking": "required",
                            "uncitedChunksTracked": True,
                            "aclEvidence": "acl_hash_only",
                            "rawAclMetadataVisible": False,
                        },
                        "citation_count": 2,
                        "chunk_count": 2,
                        "cited_chunk_count": 2,
                        "uncited_chunk_count": 0,
                        "citations": [valid_citation("doc_1:0")],
                    },
                }
            ]
        }
    )

    assert result["ok"] is False
    assert result["status"] == "failed"
    assert result["findings"] == [
        {
            "code": "rag_citation_count_mismatch",
            "section": "rag_context",
            "path": "metadata.citations",
            "citationCount": 2,
            "citationEvidenceCount": 1,
        }
    ]


def test_context_manifest_diagnostics_rejects_missing_rag_citation_ids() -> None:
    result = context_manifest_diagnostics(
        {
            "sections": [
                {
                    "name": "rag_context",
                    "content_checksum": VALID_RAG_CHECKSUM,
                    "metadata": {
                        "ragGroundingPolicy": {
                            "citationTracking": "required",
                            "uncitedChunksTracked": True,
                            "aclEvidence": "acl_hash_only",
                            "rawAclMetadataVisible": False,
                        },
                        "citation_count": 2,
                        "chunk_count": 2,
                        "cited_chunk_count": 2,
                        "uncited_chunk_count": 0,
                        "citations": [
                            valid_citation("doc_1:0"),
                            {
                                "citation_id": "",
                                "source_uri": "https://docs.example/missing",
                                "content_hash": "hash_missing",
                            },
                        ],
                    },
                }
            ]
        }
    )

    assert result["ok"] is False
    assert result["status"] == "failed"
    assert result["findings"] == [
        {
            "code": "missing_rag_citation_id",
            "section": "rag_context",
            "path": "metadata.citations[1].citation_id",
        }
    ]


def test_context_manifest_diagnostics_rejects_incomplete_rag_citation_evidence() -> None:
    result = context_manifest_diagnostics(
        {
            "sections": [
                {
                    "name": "rag_context",
                    "content_checksum": VALID_RAG_CHECKSUM,
                    "metadata": {
                        "ragGroundingPolicy": {
                            "citationTracking": "required",
                            "uncitedChunksTracked": True,
                            "aclEvidence": "acl_hash_only",
                            "rawAclMetadataVisible": False,
                        },
                        "citation_count": 2,
                        "chunk_count": 2,
                        "cited_chunk_count": 2,
                        "uncited_chunk_count": 0,
                        "citations": [
                            {"citation_id": "doc_1:0", "content_hash": "hash_1"},
                            {
                                "citation_id": "doc_2:1",
                                "source_uri": "https://docs.example/source",
                            },
                        ],
                    },
                }
            ]
        }
    )

    assert result["ok"] is False
    assert result["status"] == "failed"
    assert result["findings"] == [
        {
            "code": "missing_rag_citation_source_uri",
            "section": "rag_context",
            "path": "metadata.citations[0].source_uri",
        },
        {
            "code": "missing_rag_citation_content_hash",
            "section": "rag_context",
            "path": "metadata.citations[1].content_hash",
        },
    ]


def test_context_manifest_diagnostics_rejects_raw_acl_in_rag_citation_evidence() -> None:
    result = context_manifest_diagnostics(
        {
            "sections": [
                {
                    "name": "rag_context",
                    "content_checksum": VALID_RAG_CHECKSUM,
                    "metadata": {
                        "ragGroundingPolicy": {
                            "citationTracking": "required",
                            "uncitedChunksTracked": True,
                            "aclEvidence": "acl_hash_only",
                            "rawAclMetadataVisible": False,
                        },
                        "citation_count": 1,
                        "chunk_count": 1,
                        "cited_chunk_count": 1,
                        "uncited_chunk_count": 0,
                        "citations": [
                            {
                                "citation_id": "doc_1:0",
                                "source_uri": "https://docs.example/source",
                                "content_hash": "hash_1",
                                "acl_proof": {
                                    "tenant_id": "tenant_1",
                                    "acl_hash": "acl_1",
                                },
                            }
                        ],
                    },
                }
            ]
        }
    )

    assert result["ok"] is False
    assert result["status"] == "failed"
    assert result["rawAclMetadataVisible"] is True
    assert result["findings"] == [
        {
            "code": "raw_acl_metadata",
            "section": "rag_context",
            "path": "metadata.citations[0].acl_proof",
        },
        {
            "code": "raw_rag_citation_acl_metadata",
            "section": "rag_context",
            "path": "metadata.citations[0].acl_proof",
            "expected": "acl_hash",
        },
    ]


def test_context_manifest_diagnostics_rejects_rag_chunk_count_mismatch() -> None:
    result = context_manifest_diagnostics(
        {
            "sections": [
                {
                    "name": "rag_context",
                    "content_checksum": VALID_RAG_CHECKSUM,
                    "metadata": {
                        "ragGroundingPolicy": {
                            "citationTracking": "required",
                            "uncitedChunksTracked": True,
                            "aclEvidence": "acl_hash_only",
                            "rawAclMetadataVisible": False,
                        },
                        "citation_count": 1,
                        "chunk_count": 3,
                        "cited_chunk_count": 1,
                        "uncited_chunk_count": 1,
                        "citations": [valid_citation("doc_1:0")],
                    },
                }
            ]
        }
    )

    assert result["ok"] is False
    assert result["status"] == "failed"
    assert result["findings"] == [
        {
            "code": "rag_chunk_count_mismatch",
            "section": "rag_context",
            "path": "metadata.chunk_count",
            "chunkCount": 3,
            "citedChunkCount": 1,
            "uncitedChunkCount": 1,
        }
    ]


def test_context_manifest_diagnostics_fails_when_rag_chunks_have_no_citations() -> None:
    result = context_manifest_diagnostics(
        {
            "sections": [
                {
                    "name": "rag_context",
                    "content_checksum": VALID_RAG_CHECKSUM,
                    "metadata": {
                        "ragGroundingPolicy": {
                            "citationTracking": "required",
                            "uncitedChunksTracked": True,
                            "aclEvidence": "acl_hash_only",
                            "rawAclMetadataVisible": False,
                        },
                        "citation_count": 0,
                        "chunk_count": 2,
                        "cited_chunk_count": 0,
                        "uncited_chunk_count": 2,
                    },
                }
            ]
        }
    )

    assert result["ok"] is False
    assert result["status"] == "failed"
    assert result["findings"] == [
        {
            "code": "missing_rag_citations",
            "section": "rag_context",
            "path": "metadata.citation_count",
            "chunkCount": 2,
        }
    ]


def test_context_section_order_matches_replatform_spec() -> None:
    assert CONTEXT_SECTION_ORDER == (
        "system_policy",
        "graph_profile",
        "request_system_prompt",
        "integration_context",
        "latest_user_request",
        "approval_state",
        "session_memory",
        "rag_context",
        "recent_messages",
        "tool_outputs",
        "examples_or_rubrics",
    )


def test_trim_to_message_pair_boundary_does_not_orphan_tool_message() -> None:
    messages = [
        HumanMessage(content="hi"),
        AIMessage(content="", tool_calls=[{"name": "x", "args": {}, "id": "call_1"}]),
        ToolMessage(content="tool output", tool_call_id="call_1"),
        HumanMessage(content="next"),
    ]

    trimmed = trim_to_message_pair_boundary(messages, max_messages=2)

    assert [message.type for message in trimmed] == ["ai", "tool", "human"]
