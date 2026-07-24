from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Annotated, Any, cast

from langchain_core.tools import InjectedToolCallId, StructuredTool
from pydantic import BaseModel, Field, create_model

from reactor.kernel.citations import (
    MAX_CITATION_EVIDENCE_ITEMS,
    bounded_citation_evidence,
    citation_evidence_matches_chunk,
    is_citation_safe_id,
)
from reactor.kernel.ids import new_id
from reactor.tools.catalog import ToolSpec
from reactor.tools.execution import (
    ToolExecutionOutcome,
    ToolExecutionRequest,
    ToolExecutionResult,
    ToolHandler,
    ToolInvocationIdempotencyStore,
    ToolPolicy,
    admit_tool_execution,
    execute_tools_parallel,
    tool_invocation_record_from_outcome,
)
from reactor.tools.sanitizer import model_visible_tool_output, sanitize_tool_output

JSON_TYPE_MAP: dict[str, type[object]] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "object": dict[str, object],
    "array": list[object],
}

REACTOR_TOOL_ARTIFACT_SCHEMA = "reactor.tool_result.v1"
ToolInvocationAuditStore = ToolInvocationIdempotencyStore


def build_langchain_tools(
    tools: Sequence[ToolSpec],
    *,
    handler: ToolHandler,
    run_id: str,
    tenant_id: str,
    user_id: str,
    trusted_user_groups: tuple[str, ...] = (),
    policy: ToolPolicy | None = None,
    tool_invocation_store: ToolInvocationIdempotencyStore | None = None,
) -> list[StructuredTool]:
    return [
        build_langchain_tool(
            tool,
            handler=handler,
            run_id=run_id,
            tenant_id=tenant_id,
            user_id=user_id,
            trusted_user_groups=trusted_user_groups,
            policy=policy,
            tool_invocation_store=tool_invocation_store,
        )
        for tool in tools
        if tool.enabled
    ]


def build_langchain_tool(
    tool: ToolSpec,
    *,
    handler: ToolHandler,
    run_id: str,
    tenant_id: str,
    user_id: str,
    trusted_user_groups: tuple[str, ...] = (),
    policy: ToolPolicy | None = None,
    tool_invocation_store: ToolInvocationIdempotencyStore | None = None,
) -> StructuredTool:
    tool.validate()
    args_schema = args_schema_from_json_schema(
        tool.input_schema,
        name=f"{tool.namespace}_{tool.name}_Args",
        inject_tool_call_id=True,
    )

    async def execute(
        tool_call_id: str | None = None,
        **kwargs: Any,
    ) -> tuple[str, dict[str, object]]:
        request = ToolExecutionRequest(
            run_id=run_id,
            tenant_id=tenant_id,
            user_id=user_id,
            tool=tool,
            input_payload=kwargs,
            trusted_user_groups=trusted_user_groups,
            tool_call_id=tool_call_id,
        )
        decision = admit_tool_execution(request, policy or ToolPolicy())
        if decision.requires_approval:
            completed_at = datetime.now(UTC)
            result = ToolExecutionResult.error(
                "approval_required",
                f"approval required for {tool.qualified_name}",
            )
            await persist_langchain_tool_invocation_audit_record(
                ToolExecutionOutcome(
                    request=request,
                    result=result,
                    cache_status=None,
                    executed=False,
                ),
                tool_invocation_store=tool_invocation_store,
                started_at=completed_at,
                completed_at=completed_at,
            )
            return model_visible_langchain_tool_result(
                tool=tool,
                request=request,
                result=result,
            )
        outcome = (
            await execute_tools_parallel(
                [request],
                handler,
                idempotency_store=tool_invocation_store,
            )
        )[0]
        result = outcome.result
        return model_visible_langchain_tool_result(
            tool=tool,
            request=request,
            result=result,
        )

    return StructuredTool.from_function(
        coroutine=execute,
        name=tool.qualified_name,
        description=tool.description,
        args_schema=args_schema,
        response_format="content_and_artifact",
    )


def tool_result_envelope(
    *,
    tool: ToolSpec,
    request: ToolExecutionRequest,
    result: ToolExecutionResult,
) -> dict[str, object]:
    return {
        "schema": REACTOR_TOOL_ARTIFACT_SCHEMA,
        "status": result.status,
        "tool_id": tool.qualified_name,
        "idempotency_key": request.idempotency_key,
        "payload": model_visible_tool_output(result.payload),
    }


def model_visible_langchain_tool_result(
    *,
    tool: ToolSpec,
    request: ToolExecutionRequest,
    result: ToolExecutionResult,
) -> tuple[str, dict[str, object]]:
    envelope = tool_result_envelope(tool=tool, request=request, result=result)
    sanitized = sanitize_tool_output(
        json.dumps(envelope, sort_keys=True, separators=(",", ":")),
    )
    artifact: dict[str, object] = {
        "schema": REACTOR_TOOL_ARTIFACT_SCHEMA,
        "status": result.status,
        "tool_id": tool.qualified_name,
        "idempotency_key": request.idempotency_key,
        "model_visible_text": sanitized.model_visible_text,
        "sanitizer_findings": list(sanitized.findings),
    }
    rag_context_manifest = rag_context_manifest_metadata(tool=tool, result=result)
    if rag_context_manifest is not None:
        artifact["rag_context_manifest"] = rag_context_manifest
    return sanitized.model_visible_text, artifact


def rag_context_manifest_metadata(
    *,
    tool: ToolSpec,
    result: ToolExecutionResult,
) -> dict[str, object] | None:
    if tool.qualified_name != "Rag:hybrid_search" or result.status != "succeeded":
        return None
    return rag_context_manifest_metadata_from_payload(result.payload)


def rag_context_manifest_metadata_from_payload(
    payload: Mapping[str, object],
) -> dict[str, object] | None:
    raw_chunks = payload.get("chunks")
    chunk_count = mapping_item_count(raw_chunks)
    (
        chunk_citation_evidence,
        duplicate_chunk_citation_id_count,
        invalid_chunk_citation_id_count,
    ) = safe_chunk_citation_evidence(raw_chunks)
    raw_citations, omitted_citation_count, invalid_citation_item_count = bounded_mapping_items(
        payload.get("citations"),
        max_items=MAX_CITATION_EVIDENCE_ITEMS,
    )
    citations: list[dict[str, object]] = []
    retained_citation_ids: set[str] = set()
    invalid_citation_id_count = invalid_citation_item_count
    orphan_citation_id_count = 0
    duplicate_citation_id_count = 0
    citation_metadata_mismatch_count = 0
    for citation in raw_citations:
        bounded = bounded_citation_evidence(citation)
        citation_id = bounded.get("citation_id")
        if not isinstance(citation_id, str):
            invalid_citation_id_count += 1
            continue
        chunk_evidence = chunk_citation_evidence.get(citation_id)
        if chunk_evidence is None:
            orphan_citation_id_count += 1
            continue
        if not citation_evidence_matches_chunk(bounded, chunk_evidence):
            citation_metadata_mismatch_count += 1
            continue
        if citation_id in retained_citation_ids:
            duplicate_citation_id_count += 1
            continue
        retained_citation_ids.add(citation_id)
        citations.append(bounded)
    if (
        not chunk_count
        and not citations
        and not invalid_citation_id_count
        and not orphan_citation_id_count
        and not duplicate_citation_id_count
        and not citation_metadata_mismatch_count
        and not duplicate_chunk_citation_id_count
        and not invalid_chunk_citation_id_count
        and not omitted_citation_count
    ):
        return None
    cited_chunk_count = min(chunk_count, len(citations))
    metadata: dict[str, object] = {
        "chunk_count": chunk_count,
        "cited_chunk_count": cited_chunk_count,
        "uncited_chunk_count": max(0, chunk_count - cited_chunk_count),
        "citation_count": len(citations),
        "citations": citations,
    }
    if invalid_citation_id_count:
        metadata["invalid_citation_id_count"] = invalid_citation_id_count
    if orphan_citation_id_count:
        metadata["orphan_citation_id_count"] = orphan_citation_id_count
    if duplicate_citation_id_count:
        metadata["duplicate_citation_id_count"] = duplicate_citation_id_count
    if citation_metadata_mismatch_count:
        metadata["citation_metadata_mismatch_count"] = citation_metadata_mismatch_count
    if duplicate_chunk_citation_id_count:
        metadata["duplicate_chunk_citation_id_count"] = duplicate_chunk_citation_id_count
    if invalid_chunk_citation_id_count:
        metadata["invalid_chunk_citation_id_count"] = invalid_chunk_citation_id_count
    if omitted_citation_count:
        metadata["omitted_citation_count"] = omitted_citation_count
    if citations:
        first = citations[0]
        for key in (
            "citation_id",
            "source_uri",
            "document_id",
            "chunk_index",
            "content_hash",
            "acl_hash",
        ):
            if key in first:
                metadata[key] = first[key]
    return metadata


def bounded_mapping_items(
    value: object,
    *,
    max_items: int,
) -> tuple[list[Mapping[str, object]], int, int]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return [], 0, 0
    items: list[Mapping[str, object]] = []
    omitted_count = 0
    invalid_item_count = 0
    for item in cast(Sequence[object], value):
        if not isinstance(item, Mapping):
            invalid_item_count += 1
            continue
        if len(items) < max_items:
            items.append(cast(Mapping[str, object], item))
        else:
            omitted_count += 1
    return items, omitted_count, invalid_item_count


def mapping_item_count(value: object) -> int:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return 0
    return sum(1 for item in cast(Sequence[object], value) if isinstance(item, Mapping))


def safe_chunk_citation_evidence(
    value: object,
) -> tuple[dict[str, dict[str, object]], int, int]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return {}, 0, 0
    citations_by_id: dict[str, dict[str, object]] = {}
    duplicate_citation_ids: set[str] = set()
    duplicate_count = 0
    invalid_count = 0
    for item in cast(Sequence[object], value):
        if not isinstance(item, Mapping):
            continue
        bounded = bounded_citation_evidence(cast(Mapping[str, object], item))
        citation_id = bounded.get("citation_id")
        if not isinstance(citation_id, str) or not is_citation_safe_id(citation_id):
            invalid_count += 1
            continue
        if citation_id in duplicate_citation_ids:
            duplicate_count += 1
            continue
        if citation_id in citations_by_id:
            del citations_by_id[citation_id]
            duplicate_citation_ids.add(citation_id)
            duplicate_count += 1
            continue
        citations_by_id[citation_id] = bounded
    return citations_by_id, duplicate_count, invalid_count


async def persist_langchain_tool_invocation_audit_record(
    outcome: ToolExecutionOutcome,
    *,
    tool_invocation_store: ToolInvocationIdempotencyStore | None,
    started_at: datetime,
    completed_at: datetime,
    invocation_id: str | None = None,
) -> None:
    if tool_invocation_store is None:
        return
    record = tool_invocation_record_from_outcome(
        outcome,
        invocation_id=invocation_id or new_id("tool_invocation"),
        started_at=started_at,
        completed_at=completed_at,
    )
    try:
        await tool_invocation_store.save(record)
    except Exception:
        raise RuntimeError("tool invocation audit persistence unavailable") from None


def args_schema_from_json_schema(
    schema: Mapping[str, Any],
    *,
    name: str,
    inject_tool_call_id: bool = False,
) -> type[BaseModel]:
    properties = cast(object, schema.get("properties", {}))
    required = cast(object, schema.get("required", []))
    if not isinstance(properties, Mapping):
        properties = {}
    required_fields: set[str] = set()
    if isinstance(required, list):
        required_fields = {item for item in cast(list[object], required) if isinstance(item, str)}
    fields: dict[str, tuple[Any, Any]] = {}
    for field_name, raw_spec in cast(Mapping[object, object], properties).items():
        if not isinstance(field_name, str) or not isinstance(raw_spec, Mapping):
            continue
        typed_spec = cast(Mapping[str, Any], raw_spec)
        field_type = json_schema_field_type(typed_spec)
        description = typed_spec.get("description")
        default: Any = ... if field_name in required_fields else None
        fields[field_name] = (
            field_type,
            Field(
                default=default,
                description=description if isinstance(description, str) else None,
            ),
        )
    if inject_tool_call_id:
        fields["tool_call_id"] = (
            Annotated[str | None, InjectedToolCallId],
            None,
        )
    return create_model(name, **cast(Any, fields))


def json_schema_field_type(field_schema: Mapping[str, Any]) -> type[object]:
    raw_type = field_schema.get("type")
    if isinstance(raw_type, str):
        return JSON_TYPE_MAP.get(raw_type, object)
    return object
