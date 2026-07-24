from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import cast

from reactor.context.manifest import CONTEXT_SECTION_RANK

CONTENT_CHECKSUM_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")

RAW_ACL_METADATA_KEYS = frozenset(
    {
        "acl",
        "acl_proof",
        "acl_visibility",
        "acl_users",
        "acl_groups",
    }
)

EXPECTED_MEMORY_ADMISSION_POLICY: dict[str, object] = {
    "activeOnly": True,
    "missingStatusExcluded": True,
    "tombstonedExcluded": True,
    "supersededExcluded": True,
}
ALLOWED_MEMORY_STATUS_COUNT_LABELS = frozenset(
    {"active", "superseded", "tombstoned", "missing", "blank"}
)

EXPECTED_RAG_GROUNDING_POLICY: dict[str, object] = {
    "citationTracking": "required",
    "uncitedChunksTracked": True,
    "aclEvidence": "acl_hash_only",
    "rawAclMetadataVisible": False,
}
CONTEXT_MANIFEST_DIAGNOSTIC_CODES = frozenset(
    {
        "duplicate_context_section",
        "invalid_content_checksum",
        "invalid_memory_admission_policy",
        "invalid_rag_grounding_policy",
        "memory_active_count_mismatch",
        "memory_status_count_mismatch",
        "missing_content_checksum",
        "missing_memory_admission_policy",
        "missing_rag_citation_content_hash",
        "missing_rag_citation_evidence",
        "missing_rag_citation_id",
        "missing_rag_citation_source_uri",
        "missing_rag_citations",
        "missing_rag_grounding_policy",
        "rag_chunk_count_mismatch",
        "rag_citation_count_mismatch",
        "raw_acl_metadata",
        "raw_rag_citation_acl_metadata",
        "unknown_memory_status_count",
        "unknown_context_section",
    }
)


def context_manifest_diagnostics(context_manifest: Mapping[str, object]) -> dict[str, object]:
    sections = mapping_sequence(context_manifest.get("sections"))
    memory_policy: dict[str, object] = {}
    memory_count = 0
    skipped_memory_count = 0
    memory_status_counts: dict[str, int] = {}
    skipped_memory_status_counts: dict[str, int] = {}
    rag_policy: dict[str, object] = {}
    citation_count = 0
    chunk_count = 0
    cited_chunk_count = 0
    uncited_chunk_count = 0
    poisoned_chunk_count = 0
    poisoning_reasons: list[str] = []
    raw_acl_findings: list[dict[str, object]] = []
    missing_checksum_sections: list[str] = []
    invalid_checksum_findings: list[dict[str, object]] = []
    missing_policy_findings: list[dict[str, object]] = []
    invalid_policy_findings: list[dict[str, object]] = []
    missing_citation_findings: list[dict[str, object]] = []
    inconsistent_citation_findings: list[dict[str, object]] = []
    invalid_citation_findings: list[dict[str, object]] = []
    inconsistent_chunk_findings: list[dict[str, object]] = []
    inconsistent_memory_findings: list[dict[str, object]] = []
    duplicate_section_findings: list[dict[str, object]] = []
    unknown_section_findings: list[dict[str, object]] = []
    seen_sections: set[str] = set()
    for index, section in enumerate(sections):
        section_name = str(section.get("name", "unknown"))
        if section_name not in CONTEXT_SECTION_RANK:
            unknown_section_findings.append(
                {
                    "code": "unknown_context_section",
                    "section": section_name,
                    "path": f"sections[{index}].name",
                }
            )
        if section_name in seen_sections:
            duplicate_section_findings.append(
                {
                    "code": "duplicate_context_section",
                    "section": section_name,
                    "path": f"sections[{index}].name",
                }
            )
        seen_sections.add(section_name)
        content_checksum = section.get("content_checksum")
        if not isinstance(content_checksum, str):
            missing_checksum_sections.append(section_name)
        elif not valid_content_checksum(content_checksum):
            invalid_checksum_findings.append(
                {
                    "code": "invalid_content_checksum",
                    "section": section_name,
                    "path": "content_checksum",
                    "expected": "sha256:<64-hex>",
                    "actual": content_checksum,
                }
            )
        metadata = optional_mapping(section.get("metadata"))
        if section_name == "session_memory":
            memory_policy = dict(optional_mapping(metadata.get("memoryAdmissionPolicy")))
            if not memory_policy:
                missing_policy_findings.append(
                    {
                        "code": "missing_memory_admission_policy",
                        "section": section_name,
                        "path": "metadata.memoryAdmissionPolicy",
                    }
                )
            else:
                invalid_policy_findings.extend(
                    policy_contract_findings(
                        "invalid_memory_admission_policy",
                        section_name,
                        "metadata.memoryAdmissionPolicy",
                        memory_policy,
                        EXPECTED_MEMORY_ADMISSION_POLICY,
                    )
                )
            memory_count = nonnegative_int_metadata(metadata.get("memory_count"))
            skipped_memory_count = nonnegative_int_metadata(metadata.get("skipped_memory_count"))
            memory_status_counts = nonnegative_int_mapping(metadata.get("status_counts"))
            skipped_memory_status_counts = nonnegative_int_mapping(
                metadata.get("skipped_status_counts")
            )
            if memory_status_counts:
                for status in sorted(
                    set(memory_status_counts) - ALLOWED_MEMORY_STATUS_COUNT_LABELS
                ):
                    inconsistent_memory_findings.append(
                        {
                            "code": "unknown_memory_status_count",
                            "section": section_name,
                            "path": f"metadata.status_counts.{status}",
                            "status": status,
                        }
                    )
                total_status_count = sum(memory_status_counts.values())
                if total_status_count != memory_count + skipped_memory_count:
                    inconsistent_memory_findings.append(
                        {
                            "code": "memory_status_count_mismatch",
                            "section": section_name,
                            "path": "metadata.status_counts",
                            "memoryCount": memory_count,
                            "skippedMemoryCount": skipped_memory_count,
                            "statusCountTotal": total_status_count,
                        }
                    )
                active_status_count = memory_status_counts.get("active", 0)
                if active_status_count != memory_count:
                    inconsistent_memory_findings.append(
                        {
                            "code": "memory_active_count_mismatch",
                            "section": section_name,
                            "path": "metadata.status_counts.active",
                            "memoryCount": memory_count,
                            "activeStatusCount": active_status_count,
                        }
                    )
            if skipped_memory_status_counts:
                for status in sorted(
                    set(skipped_memory_status_counts) - ALLOWED_MEMORY_STATUS_COUNT_LABELS
                ):
                    inconsistent_memory_findings.append(
                        {
                            "code": "unknown_memory_status_count",
                            "section": section_name,
                            "path": f"metadata.skipped_status_counts.{status}",
                            "status": status,
                        }
                    )
                if skipped_memory_status_counts.get("active", 0) > 0:
                    inconsistent_memory_findings.append(
                        {
                            "code": "memory_active_count_mismatch",
                            "section": section_name,
                            "path": "metadata.skipped_status_counts.active",
                            "memoryCount": memory_count,
                            "activeStatusCount": skipped_memory_status_counts["active"],
                        }
                    )
                skipped_status_total = sum(skipped_memory_status_counts.values())
                if skipped_status_total != skipped_memory_count:
                    inconsistent_memory_findings.append(
                        {
                            "code": "memory_status_count_mismatch",
                            "section": section_name,
                            "path": "metadata.skipped_status_counts",
                            "skippedMemoryCount": skipped_memory_count,
                            "statusCountTotal": skipped_status_total,
                        }
                    )
        if section_name == "rag_context":
            rag_policy = dict(optional_mapping(metadata.get("ragGroundingPolicy")))
            if not rag_policy:
                missing_policy_findings.append(
                    {
                        "code": "missing_rag_grounding_policy",
                        "section": section_name,
                        "path": "metadata.ragGroundingPolicy",
                    }
                )
            else:
                invalid_policy_findings.extend(
                    policy_contract_findings(
                        "invalid_rag_grounding_policy",
                        section_name,
                        "metadata.ragGroundingPolicy",
                        rag_policy,
                        EXPECTED_RAG_GROUNDING_POLICY,
                    )
                )
            raw_citation_count = metadata.get("citation_count")
            if isinstance(raw_citation_count, int) and not isinstance(raw_citation_count, bool):
                citation_count = raw_citation_count
            citation_evidence = mapping_sequence(metadata.get("citations"))
            citation_evidence_count = len(citation_evidence)
            if citation_count > 0 and citation_evidence_count == 0:
                missing_citation_findings.append(
                    {
                        "code": "missing_rag_citation_evidence",
                        "section": section_name,
                        "path": "metadata.citations",
                        "citationCount": citation_count,
                    }
                )
            if citation_evidence_count > 0 and citation_count != citation_evidence_count:
                inconsistent_citation_findings.append(
                    {
                        "code": "rag_citation_count_mismatch",
                        "section": section_name,
                        "path": "metadata.citations",
                        "citationCount": citation_count,
                        "citationEvidenceCount": citation_evidence_count,
                    }
                )
            invalid_citation_findings.extend(
                invalid_citation_evidence_findings(section_name, citation_evidence)
            )
            chunk_count = nonnegative_int_metadata(metadata.get("chunk_count"))
            cited_chunk_count = nonnegative_int_metadata(metadata.get("cited_chunk_count"))
            uncited_chunk_count = nonnegative_int_metadata(metadata.get("uncited_chunk_count"))
            poisoned_chunk_count = nonnegative_int_metadata(metadata.get("poisoned_chunk_count"))
            poisoning_reasons = string_sequence(metadata.get("poisoning_reasons"))
            if chunk_count != cited_chunk_count + uncited_chunk_count:
                inconsistent_chunk_findings.append(
                    {
                        "code": "rag_chunk_count_mismatch",
                        "section": section_name,
                        "path": "metadata.chunk_count",
                        "chunkCount": chunk_count,
                        "citedChunkCount": cited_chunk_count,
                        "uncitedChunkCount": uncited_chunk_count,
                    }
                )
            if chunk_count > 0 and citation_count == 0:
                missing_citation_findings.append(
                    {
                        "code": "missing_rag_citations",
                        "section": section_name,
                        "path": "metadata.citation_count",
                        "chunkCount": chunk_count,
                    }
                )
        raw_acl_findings.extend(raw_acl_metadata_findings(section_name, metadata))
    findings: list[dict[str, object]] = [
        *raw_acl_findings,
        *invalid_checksum_findings,
        *missing_policy_findings,
        *invalid_policy_findings,
        *missing_citation_findings,
        *inconsistent_citation_findings,
        *invalid_citation_findings,
        *inconsistent_chunk_findings,
        *inconsistent_memory_findings,
        *duplicate_section_findings,
        *unknown_section_findings,
    ]
    findings.extend(
        {"code": "missing_content_checksum", "section": section_name}
        for section_name in missing_checksum_sections
    )
    return {
        "ok": not findings,
        "status": "passed" if not findings else "failed",
        "sectionCount": len(sections),
        "memoryAdmissionPolicy": memory_policy,
        "memoryCount": memory_count,
        "skippedMemoryCount": skipped_memory_count,
        "skippedMemoryStatusCounts": skipped_memory_status_counts,
        "memoryStatusCounts": memory_status_counts,
        "ragGroundingPolicy": rag_policy,
        "citationCount": citation_count,
        "chunkCount": chunk_count,
        "citedChunkCount": cited_chunk_count,
        "uncitedChunkCount": uncited_chunk_count,
        "poisoningCoverage": {
            "status": "verified" if poisoned_chunk_count > 0 else "not_exercised",
            "poisonedChunkCount": poisoned_chunk_count,
            "poisoningReasons": poisoning_reasons,
            "source": "rag_tool_context_manifest",
        },
        "rawAclMetadataVisible": bool(raw_acl_findings),
        "findings": findings,
    }


def valid_content_checksum(value: str) -> bool:
    return CONTENT_CHECKSUM_PATTERN.fullmatch(value) is not None


def invalid_citation_evidence_findings(
    section_name: str,
    citations: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for index, citation in enumerate(citations):
        citation_id = citation.get("citation_id")
        if not isinstance(citation_id, str) or not citation_id.strip():
            findings.append(
                {
                    "code": "missing_rag_citation_id",
                    "section": section_name,
                    "path": f"metadata.citations[{index}].citation_id",
                }
            )
        source_uri = citation.get("source_uri")
        if not isinstance(source_uri, str) or not source_uri.strip():
            findings.append(
                {
                    "code": "missing_rag_citation_source_uri",
                    "section": section_name,
                    "path": f"metadata.citations[{index}].source_uri",
                }
            )
        content_hash = citation.get("content_hash")
        if not isinstance(content_hash, str) or not content_hash.strip():
            findings.append(
                {
                    "code": "missing_rag_citation_content_hash",
                    "section": section_name,
                    "path": f"metadata.citations[{index}].content_hash",
                }
            )
        for key in citation:
            if raw_acl_metadata_key(key):
                findings.append(
                    {
                        "code": "raw_rag_citation_acl_metadata",
                        "section": section_name,
                        "path": f"metadata.citations[{index}].{key}",
                        "expected": "acl_hash",
                    }
                )
    return findings


def policy_contract_findings(
    code: str,
    section_name: str,
    path: str,
    policy: Mapping[str, object],
    expected_policy: Mapping[str, object],
) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for key, expected in expected_policy.items():
        actual = policy.get(key)
        if actual != expected:
            findings.append(
                {
                    "code": code,
                    "section": section_name,
                    "path": f"{path}.{key}",
                    "expected": expected,
                    "actual": actual,
                }
            )
    return findings


def raw_acl_metadata_findings(
    section_name: str,
    value: object,
    *,
    path: str = "metadata",
) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    if isinstance(value, Mapping):
        for key, child in cast(Mapping[str, object], value).items():
            child_path = f"{path}.{key}"
            if raw_acl_metadata_key(key):
                findings.append(
                    {
                        "code": "raw_acl_metadata",
                        "section": section_name,
                        "path": child_path,
                    }
                )
            findings.extend(raw_acl_metadata_findings(section_name, child, path=child_path))
    elif isinstance(value, Sequence) and not isinstance(value, str | bytes):
        children = cast(Sequence[object], value)
        for index, child in enumerate(children):
            findings.extend(raw_acl_metadata_findings(section_name, child, path=f"{path}[{index}]"))
    return findings


def raw_acl_metadata_key(key: str) -> bool:
    return (
        key in RAW_ACL_METADATA_KEYS or key.startswith("acl_user_") or key.startswith("acl_group_")
    )


def nonnegative_int_metadata(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return 0


def nonnegative_int_mapping(value: object) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, int] = {}
    for key, item in cast(Mapping[object, object], value).items():
        if (
            isinstance(key, str)
            and isinstance(item, int)
            and not isinstance(item, bool)
            and item >= 0
        ):
            result[key] = item
    return result


def optional_mapping(value: object) -> Mapping[str, object]:
    return cast(Mapping[str, object], value) if isinstance(value, Mapping) else {}


def mapping_sequence(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return []
    items = cast(Sequence[object], value)
    return [cast(Mapping[str, object], item) for item in items if isinstance(item, Mapping)]


def string_sequence(value: object) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return []
    items = cast(Sequence[object], value)
    return [item.strip() for item in items if isinstance(item, str) and item.strip()]
