from __future__ import annotations

import re
from collections.abc import Mapping
from typing import cast

CITATION_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")
MAX_CITATION_EVIDENCE_ITEMS = 20
BOUNDED_CITATION_TEXT_LIMITS = {
    "citation_id": 256,
    "source_uri": 2_048,
    "document_id": 256,
    "content_hash": 256,
    "acl_hash": 256,
}
CITATION_PROVENANCE_FIELDS = ("source_uri", "document_id", "chunk_index", "content_hash")


def is_citation_safe_id(value: str) -> bool:
    stripped = value.strip()
    return (
        bool(stripped) and stripped == value and CITATION_SAFE_ID_RE.fullmatch(stripped) is not None
    )


def bounded_citation_evidence(citation: Mapping[str, object]) -> dict[str, object]:
    bounded: dict[str, object] = {}
    for key, max_length in BOUNDED_CITATION_TEXT_LIMITS.items():
        value = citation.get(key)
        if not isinstance(value, str):
            continue
        normalized = value.strip()
        if not normalized or len(normalized) > max_length:
            continue
        if key == "citation_id" and not is_citation_safe_id(value):
            continue
        bounded[key] = normalized
    chunk_index = citation.get("chunk_index")
    if isinstance(chunk_index, int) and not isinstance(chunk_index, bool):
        bounded["chunk_index"] = chunk_index
    if "acl_hash" not in bounded:
        acl_proof = citation.get("acl_proof")
        if isinstance(acl_proof, Mapping):
            acl_hash = cast(Mapping[object, object], acl_proof).get("acl_hash")
            if (
                isinstance(acl_hash, str)
                and acl_hash.strip()
                and len(acl_hash.strip()) <= BOUNDED_CITATION_TEXT_LIMITS["acl_hash"]
            ):
                bounded["acl_hash"] = acl_hash.strip()
    return bounded


def citation_evidence_matches_chunk(
    citation: Mapping[str, object],
    chunk: Mapping[str, object],
) -> bool:
    return all(
        field not in citation or field not in chunk or citation[field] == chunk[field]
        for field in CITATION_PROVENANCE_FIELDS
    )
