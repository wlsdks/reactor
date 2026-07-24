from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from hashlib import sha256
from typing import cast

CONTEXT_SECTION_ORDER = (
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

CONTEXT_SECTION_RANK = {
    section_name: index for index, section_name in enumerate(CONTEXT_SECTION_ORDER)
}

ACL_MARKER_RE = re.compile(r"(?im)^.*\bacl_(?:user|group)_[A-Za-z0-9_:-]+.*$")
ACL_MAPPING_RE = re.compile(r"(?im)^.*\bacl\s*[:=]\s*[\[{].*$")
ACL_METADATA_RE = re.compile(r"(?im)^.*\bacl_(?:visibility|users|groups)\s*[:=].*$")
UNSAFE_MANIFEST_METADATA_KEYS = frozenset(
    {
        "acl",
        "acl_proof",
        "acl_visibility",
        "acl_users",
        "acl_groups",
    }
)


def empty_metadata() -> dict[str, object]:
    return {}


@dataclass(frozen=True)
class ContextSection:
    name: str
    content: str
    source_type: str = "internal"
    tenant_id: str | None = None
    tainted: bool = False
    metadata: Mapping[str, object] = field(default_factory=empty_metadata)

    def validate(self) -> None:
        if self.name not in CONTEXT_SECTION_RANK:
            raise ValueError(f"unknown context section: {self.name}")
        if not self.source_type.strip():
            raise ValueError("context section source_type is required")

    def model_visible_content(self) -> str:
        if not self.tainted:
            return self.content
        return redact_internal_acl_markers(self.content)

    def manifest_entry(self) -> dict[str, object]:
        self.validate()
        content_checksum = f"sha256:{sha256(self.model_visible_content().encode()).hexdigest()}"
        entry: dict[str, object] = {
            "name": self.name,
            "source_type": self.source_type,
            "tenant_id": self.tenant_id,
            "tainted": self.tainted,
            "content_length": len(self.content),
            "content_checksum": content_checksum,
            "metadata": safe_manifest_metadata(self.metadata),
        }
        if self.tenant_id is None:
            entry.pop("tenant_id")
        return entry


@dataclass(frozen=True)
class ContextManifest:
    sections: list[ContextSection]

    def ordered_sections(self) -> list[ContextSection]:
        for section in self.sections:
            section.validate()
        return sorted(self.sections, key=lambda section: CONTEXT_SECTION_RANK[section.name])

    def render(self) -> str:
        return "\n\n".join(
            f"[{section.name}]\n{section.model_visible_content()}"
            for section in self.ordered_sections()
        )

    def as_manifest(self) -> dict[str, object]:
        return {"sections": [section.manifest_entry() for section in self.ordered_sections()]}


def redact_internal_acl_markers(content: str) -> str:
    redacted = ACL_MARKER_RE.sub("[REDACTED_INTERNAL_ACL_MARKER]", content)
    redacted = ACL_MAPPING_RE.sub("[REDACTED_INTERNAL_ACL_METADATA]", redacted)
    return ACL_METADATA_RE.sub("[REDACTED_INTERNAL_ACL_METADATA]", redacted)


def safe_manifest_metadata(metadata: Mapping[str, object]) -> dict[str, object]:
    safe: dict[str, object] = {}
    for key, value in metadata.items():
        safe_key = str(key)
        if is_authorization_metadata_key(safe_key):
            continue
        safe_value = safe_manifest_value(value)
        if safe_value is not _UNSAFE_METADATA:
            safe[safe_key] = safe_value
    return safe


_UNSAFE_METADATA = object()


def is_authorization_metadata_key(key: str) -> bool:
    normalized = key.strip().lower()
    return normalized in UNSAFE_MANIFEST_METADATA_KEYS or normalized.startswith(
        ("acl_user_", "acl_group_")
    )


def safe_manifest_value(value: object) -> object:
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    if isinstance(value, Mapping):
        safe_mapping = safe_manifest_metadata(cast(Mapping[str, object], value))
        return safe_mapping if safe_mapping else _UNSAFE_METADATA
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        values = cast(Sequence[object], value)
        safe_items: list[object] = []
        for item in values:
            safe_item = safe_manifest_value(item)
            if safe_item is not _UNSAFE_METADATA:
                safe_items.append(safe_item)
        return safe_items
    return _UNSAFE_METADATA
