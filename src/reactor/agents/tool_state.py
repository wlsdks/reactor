from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from reactor.tools.catalog import ToolSpec

PENDING_TOOL_REQUEST_SCHEMA_VERSION = "reactor.pending_tool_request.v1"


@dataclass(frozen=True)
class PendingToolRequest:
    tool: ToolSpec
    input_payload: dict[str, object]


def normalize_pending_tool_request_update(
    _current: dict[str, object] | None,
    update: dict[str, object] | None,
) -> dict[str, object]:
    if update is None or not update:
        return {}
    return pending_tool_request_to_state_payload(update)


def normalize_pending_tool_requests_update(
    _current: list[dict[str, object]] | None,
    update: list[dict[str, object]] | None,
) -> list[dict[str, object]]:
    if update is None:
        return []
    return [pending_tool_request_to_state_payload(item) for item in update]


def pending_tool_request_to_state_payload(raw_request: Mapping[str, object]) -> dict[str, object]:
    parsed = pending_tool_request_from_raw(raw_request)
    return {
        "schema_version": PENDING_TOOL_REQUEST_SCHEMA_VERSION,
        "tool": tool_spec_to_state_payload(parsed.tool),
        "input_payload": json_safe_object(
            parsed.input_payload,
            path="pending_tool_request.input_payload",
        ),
    }


def tool_spec_to_state_payload(tool: ToolSpec) -> dict[str, object]:
    tool.validate()
    payload: dict[str, object] = {
        "tenant_id": tool.tenant_id,
        "namespace": tool.namespace,
        "name": tool.name,
        "description": tool.description,
        "risk_level": tool.risk_level,
        "input_schema": json_safe_object(
            tool.input_schema,
            path="pending_tool_request.tool.input_schema",
        ),
        "output_schema": json_safe_object(
            tool.output_schema,
            path="pending_tool_request.tool.output_schema",
        ),
        "enabled": tool.enabled,
        "requires_approval": tool.requires_approval,
        "timeout_ms": tool.timeout_ms,
    }
    if tool.catalog_id is not None:
        payload["catalog_id"] = tool.catalog_id
    return payload


def pending_tool_request_from_raw(raw_request: Mapping[str, object]) -> PendingToolRequest:
    schema_version = raw_request.get("schema_version")
    if schema_version is not None and schema_version != PENDING_TOOL_REQUEST_SCHEMA_VERSION:
        raise ValueError(f"unsupported pending_tool_request schema_version: {schema_version!r}")
    tool_spec = tool_spec_from_raw(raw_request.get("tool"))
    input_payload = raw_request.get("input_payload")
    if not isinstance(input_payload, Mapping):
        raise ValueError("pending_tool_request.input_payload must be an object")
    typed_input_payload = cast(Mapping[Any, Any], input_payload)
    return PendingToolRequest(
        tool=tool_spec,
        input_payload=json_safe_object(
            typed_input_payload,
            path="pending_tool_request.input_payload",
        ),
    )


def tool_spec_from_raw(raw_tool: object) -> ToolSpec:
    if isinstance(raw_tool, ToolSpec):
        raw_tool.validate()
        return raw_tool
    if not isinstance(raw_tool, Mapping):
        raise ValueError("pending_tool_request.tool must be a ToolSpec or object")
    tool_payload = cast(Mapping[Any, Any], raw_tool)
    input_schema = tool_payload.get("input_schema")
    output_schema = tool_payload.get("output_schema")
    if not isinstance(input_schema, Mapping) or not isinstance(output_schema, Mapping):
        raise ValueError("pending_tool_request.tool schemas must be objects")
    typed_input_schema = cast(Mapping[Any, Any], input_schema)
    typed_output_schema = cast(Mapping[Any, Any], output_schema)
    requires_approval = tool_payload.get("requires_approval")
    if requires_approval is not None and not isinstance(requires_approval, bool):
        raise ValueError("pending_tool_request.tool.requires_approval must be boolean")
    enabled = tool_payload.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ValueError("pending_tool_request.tool.enabled must be boolean")
    timeout_ms = tool_payload.get("timeout_ms", 15_000)
    if not isinstance(timeout_ms, int) or isinstance(timeout_ms, bool):
        raise ValueError("pending_tool_request.tool.timeout_ms must be integer")
    catalog_id = tool_payload.get("catalog_id")
    if catalog_id is not None and not isinstance(catalog_id, str):
        raise ValueError("pending_tool_request.tool.catalog_id must be a string")
    spec = ToolSpec(
        tenant_id=required_tool_string(tool_payload, "tenant_id"),
        namespace=required_tool_string(tool_payload, "namespace"),
        name=required_tool_string(tool_payload, "name"),
        description=required_tool_string(tool_payload, "description"),
        risk_level=required_tool_string(tool_payload, "risk_level"),
        input_schema=json_safe_object(
            typed_input_schema,
            path="pending_tool_request.tool.input_schema",
        ),
        output_schema=json_safe_object(
            typed_output_schema,
            path="pending_tool_request.tool.output_schema",
        ),
        enabled=enabled,
        requires_approval=requires_approval,
        timeout_ms=timeout_ms,
        catalog_id=catalog_id,
    )
    spec.validate()
    return spec


def required_tool_string(payload: Mapping[Any, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"pending_tool_request.tool.{key} is required")
    return value


def json_safe_object(value: Mapping[Any, Any], *, path: str) -> dict[str, object]:
    normalized = _json_safe_value(value, path=path, ancestors=set())
    return cast(dict[str, object], normalized)


def _json_safe_value(value: object, *, path: str, ancestors: set[int]) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} must not contain non-finite numbers")
        return value
    if isinstance(value, Mapping):
        typed_mapping = cast(Mapping[Any, Any], value)
        value_id = id(cast(object, value))
        if value_id in ancestors:
            raise ValueError(f"{path} must not contain cycles")
        ancestors.add(value_id)
        try:
            normalized: dict[str, object] = {}
            for key, item in typed_mapping.items():
                if not isinstance(key, str):
                    raise ValueError(f"{path} keys must be strings")
                normalized[key] = _json_safe_value(
                    item,
                    path=f"{path}.{key}",
                    ancestors=ancestors,
                )
            return normalized
        finally:
            ancestors.remove(value_id)
    if isinstance(value, (list, tuple)):
        typed_sequence = cast(list[Any] | tuple[Any, ...], value)
        value_id = id(cast(object, value))
        if value_id in ancestors:
            raise ValueError(f"{path} must not contain cycles")
        ancestors.add(value_id)
        try:
            return [
                _json_safe_value(item, path=f"{path}[{index}]", ancestors=ancestors)
                for index, item in enumerate(typed_sequence)
            ]
        finally:
            ancestors.remove(value_id)
    raise ValueError(f"{path} contains unsupported value type: {type(value).__name__}")
