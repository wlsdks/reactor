from __future__ import annotations

import asyncio
import copy
import json
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

import yaml
from jsonschema import SchemaError, ValidationError
from jsonschema.exceptions import UnknownType
from jsonschema.validators import Draft202012Validator

from reactor.kernel.citations import is_citation_safe_id


class ResponseFormat(StrEnum):
    TEXT = "TEXT"
    JSON = "JSON"
    YAML = "YAML"


@dataclass(frozen=True)
class StructuredOutputResult:
    success: bool
    content: str | None = None
    error_code: str | None = None


RepairCallback = Callable[[str, ResponseFormat], str | Awaitable[str | None] | None]


class StructuredOutputValidator:
    def is_valid_format(
        self,
        content: str,
        response_format: ResponseFormat,
        *,
        schema: Mapping[str, object] | None = None,
    ) -> bool:
        match response_format:
            case ResponseFormat.TEXT:
                return True
            case ResponseFormat.JSON:
                return self._validate_json(content, schema=schema)
            case ResponseFormat.YAML:
                return self._validate_yaml(content, schema=schema)

    def strip_markdown_code_fence(self, content: str) -> str:
        trimmed = content.strip()
        if not trimmed.startswith("```"):
            return trimmed
        lines = trimmed.splitlines()
        if not lines:
            return trimmed
        body = lines[1:]
        if body and body[-1].strip() == "```":
            body = body[:-1]
        return "\n".join(body).strip()

    def _validate_json(self, content: str, *, schema: Mapping[str, object] | None = None) -> bool:
        try:
            parsed = json.loads(content)
            if schema is not None:
                Draft202012Validator(schema).validate(parsed)
                return True
            if not isinstance(parsed, dict):
                return False
        except (json.JSONDecodeError, SchemaError, UnknownType, ValidationError):
            return False
        return True

    def _validate_yaml(self, content: str, *, schema: Mapping[str, object] | None = None) -> bool:
        try:
            parsed = yaml.safe_load(content)
            if schema is not None:
                Draft202012Validator(schema).validate(parsed)
        except (SchemaError, UnknownType, ValidationError, yaml.YAMLError):
            return False
        return isinstance(parsed, dict | list)


class StructuredResponseRepairer:
    MAX_REPAIR_INPUT_CHARS = 8_192

    def __init__(
        self,
        *,
        repair_callback: RepairCallback | None = None,
        validator: StructuredOutputValidator | None = None,
        max_repair_input_chars: int = MAX_REPAIR_INPUT_CHARS,
    ) -> None:
        self._repair_callback = repair_callback
        self._validator = validator or StructuredOutputValidator()
        self._max_repair_input_chars = max(0, max_repair_input_chars)

    async def validate_and_repair(
        self,
        raw_content: str,
        response_format: ResponseFormat,
        *,
        schema: Mapping[str, object] | None = None,
    ) -> StructuredOutputResult:
        if response_format == ResponseFormat.TEXT:
            return StructuredOutputResult(success=True, content=raw_content)
        stripped = self._validator.strip_markdown_code_fence(raw_content)
        if self._validator.is_valid_format(stripped, response_format, schema=schema):
            return StructuredOutputResult(success=True, content=stripped)
        repaired = await self._attempt_repair(stripped, response_format)
        if repaired is not None and self._validator.is_valid_format(
            repaired,
            response_format,
            schema=schema,
        ):
            return StructuredOutputResult(success=True, content=repaired)
        return StructuredOutputResult(success=False, error_code="INVALID_RESPONSE")

    async def _attempt_repair(
        self,
        invalid_content: str,
        response_format: ResponseFormat,
    ) -> str | None:
        if self._repair_callback is None:
            return None
        bounded = invalid_content[: self._max_repair_input_chars]
        try:
            repaired = self._repair_callback(bounded, response_format)
            if asyncio.iscoroutine(repaired) or isinstance(repaired, Awaitable):
                repaired = await repaired
        except asyncio.CancelledError:
            raise
        except Exception:
            return None
        if repaired is None:
            return None
        return self._validator.strip_markdown_code_fence(str(repaired))


def extract_response_format(value: object) -> ResponseFormat:
    if isinstance(value, ResponseFormat):
        return value
    if isinstance(value, str):
        normalized = re.sub(r"[^A-Za-z]", "", value).upper()
        if normalized in ResponseFormat:
            return ResponseFormat(normalized)
    return ResponseFormat.TEXT


def merge_citation_response_schema(
    schema: Mapping[str, object] | None,
    context_manifest: Mapping[str, object] | None,
) -> dict[str, object] | None:
    citation_ids = context_manifest_citation_ids(context_manifest)
    if not context_manifest_requires_citations(context_manifest):
        return copy.deepcopy(dict(schema)) if schema is not None else None

    merged: dict[str, object] = copy.deepcopy(dict(schema or {}))
    merged["type"] = "object"
    properties = mutable_mapping(merged.get("properties"))
    properties["citations"] = {
        "type": "array",
        "items": {"type": "string", "enum": citation_ids},
        "minItems": 1,
        "uniqueItems": True,
    }
    merged["properties"] = properties
    required = list(dict.fromkeys([*string_sequence(merged.get("required")), "citations"]))
    merged["required"] = required
    return merged


def context_manifest_requires_citations(context_manifest: Mapping[str, object] | None) -> bool:
    if context_manifest is None:
        return False
    rag_context = context_manifest_section(context_manifest, "rag_context")
    metadata = optional_mapping(rag_context.get("metadata"))
    return (
        positive_int(metadata.get("chunk_count"))
        or bool(context_manifest_raw_citation_ids(context_manifest))
        or context_manifest_invalid_citation_id_count(context_manifest) > 0
        or context_manifest_orphan_citation_id_count(context_manifest) > 0
        or context_manifest_duplicate_citation_id_count(context_manifest) > 0
        or context_manifest_citation_metadata_mismatch_count(context_manifest) > 0
        or context_manifest_duplicate_chunk_citation_id_count(context_manifest) > 0
        or context_manifest_invalid_chunk_citation_id_count(context_manifest) > 0
        or context_manifest_omitted_citation_count(context_manifest) > 0
        or context_manifest_invalid_runtime_rag_artifact_count(context_manifest) > 0
    )


def context_manifest_citation_ids(context_manifest: Mapping[str, object] | None) -> list[str]:
    return [
        citation_id
        for citation_id in context_manifest_raw_citation_ids(context_manifest)
        if is_citation_safe_id(citation_id)
    ]


def context_manifest_unsafe_citation_ids(
    context_manifest: Mapping[str, object] | None,
) -> list[str]:
    return [
        citation_id
        for citation_id in context_manifest_raw_citation_ids(context_manifest)
        if not is_citation_safe_id(citation_id)
    ]


def context_manifest_unsafe_citation_count(
    context_manifest: Mapping[str, object] | None,
) -> int:
    return (
        len(context_manifest_unsafe_citation_ids(context_manifest))
        + context_manifest_invalid_citation_id_count(context_manifest)
        + context_manifest_orphan_citation_id_count(context_manifest)
        + context_manifest_duplicate_citation_id_count(context_manifest)
        + context_manifest_citation_metadata_mismatch_count(context_manifest)
        + context_manifest_duplicate_chunk_citation_id_count(context_manifest)
        + context_manifest_invalid_chunk_citation_id_count(context_manifest)
        + context_manifest_omitted_citation_count(context_manifest)
        + context_manifest_invalid_runtime_rag_artifact_count(context_manifest)
    )


def context_manifest_invalid_citation_id_count(
    context_manifest: Mapping[str, object] | None,
) -> int:
    if context_manifest is None:
        return 0
    rag_context = context_manifest_section(context_manifest, "rag_context")
    metadata = optional_mapping(rag_context.get("metadata"))
    value = metadata.get("invalid_citation_id_count")
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def context_manifest_orphan_citation_id_count(
    context_manifest: Mapping[str, object] | None,
) -> int:
    if context_manifest is None:
        return 0
    rag_context = context_manifest_section(context_manifest, "rag_context")
    metadata = optional_mapping(rag_context.get("metadata"))
    value = metadata.get("orphan_citation_id_count")
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def context_manifest_duplicate_citation_id_count(
    context_manifest: Mapping[str, object] | None,
) -> int:
    if context_manifest is None:
        return 0
    rag_context = context_manifest_section(context_manifest, "rag_context")
    metadata = optional_mapping(rag_context.get("metadata"))
    value = metadata.get("duplicate_citation_id_count")
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def context_manifest_citation_metadata_mismatch_count(
    context_manifest: Mapping[str, object] | None,
) -> int:
    if context_manifest is None:
        return 0
    rag_context = context_manifest_section(context_manifest, "rag_context")
    metadata = optional_mapping(rag_context.get("metadata"))
    value = metadata.get("citation_metadata_mismatch_count")
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def context_manifest_duplicate_chunk_citation_id_count(
    context_manifest: Mapping[str, object] | None,
) -> int:
    if context_manifest is None:
        return 0
    rag_context = context_manifest_section(context_manifest, "rag_context")
    metadata = optional_mapping(rag_context.get("metadata"))
    value = metadata.get("duplicate_chunk_citation_id_count")
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def context_manifest_invalid_chunk_citation_id_count(
    context_manifest: Mapping[str, object] | None,
) -> int:
    if context_manifest is None:
        return 0
    rag_context = context_manifest_section(context_manifest, "rag_context")
    metadata = optional_mapping(rag_context.get("metadata"))
    value = metadata.get("invalid_chunk_citation_id_count")
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def context_manifest_omitted_citation_count(
    context_manifest: Mapping[str, object] | None,
) -> int:
    if context_manifest is None:
        return 0
    rag_context = context_manifest_section(context_manifest, "rag_context")
    metadata = optional_mapping(rag_context.get("metadata"))
    value = metadata.get("omitted_citation_count")
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def context_manifest_invalid_runtime_rag_artifact_count(
    context_manifest: Mapping[str, object] | None,
) -> int:
    if context_manifest is None:
        return 0
    rag_context = context_manifest_section(context_manifest, "rag_context")
    metadata = optional_mapping(rag_context.get("metadata"))
    value = metadata.get("invalid_runtime_rag_artifact_count")
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def context_manifest_raw_citation_ids(
    context_manifest: Mapping[str, object] | None,
) -> list[str]:
    if context_manifest is None:
        return []
    rag_context = context_manifest_section(context_manifest, "rag_context")
    metadata = optional_mapping(rag_context.get("metadata"))
    citation_ids: list[str] = []
    single_citation_id = metadata.get("citation_id")
    if isinstance(single_citation_id, str) and single_citation_id:
        citation_ids.append(single_citation_id)
    citations = metadata.get("citations")
    if not isinstance(citations, Sequence) or isinstance(citations, str | bytes):
        return list(dict.fromkeys(citation_ids))
    citation_items = cast(Sequence[object], citations)
    for citation in citation_items:
        citation_mapping = optional_mapping(citation)
        citation_id = citation_mapping.get("citation_id")
        if isinstance(citation_id, str) and citation_id:
            citation_ids.append(citation_id)
    return list(dict.fromkeys(citation_ids))


def context_manifest_section(
    context_manifest: Mapping[str, object],
    section_name: str,
) -> Mapping[str, object]:
    sections = context_manifest.get("sections")
    if isinstance(sections, Mapping):
        section_mapping = cast(Mapping[str, object], sections)
        return optional_mapping(section_mapping.get(section_name))
    if isinstance(sections, Sequence) and not isinstance(sections, str | bytes):
        section_items = cast(Sequence[object], sections)
        for section in section_items:
            section_mapping = optional_mapping(section)
            if section_mapping.get("name") == section_name:
                return section_mapping
    return {}


def optional_mapping(value: object) -> Mapping[str, object]:
    return cast(Mapping[str, object], value) if isinstance(value, Mapping) else {}


def mutable_mapping(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    return copy.deepcopy(dict(cast(Mapping[str, object], value)))


def string_sequence(value: object) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return []
    return [item for item in cast(Sequence[object], value) if isinstance(item, str)]


def positive_int(value: object) -> bool:
    return isinstance(value, int) and value > 0
