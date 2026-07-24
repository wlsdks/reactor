from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

RISK_LEVELS = {"read", "write", "external_side_effect", "destructive"}
APPROVAL_REQUIRED_RISKS = {"write", "external_side_effect", "destructive"}
RESERVED_LANGCHAIN_TOOL_ARGUMENTS = frozenset({"config", "runtime", "tool_call_id"})


@dataclass(frozen=True)
class ToolSpec:
    tenant_id: str
    namespace: str
    name: str
    description: str
    risk_level: str
    input_schema: Mapping[str, Any]
    output_schema: Mapping[str, Any]
    enabled: bool = True
    requires_approval: bool | None = None
    timeout_ms: int = 15_000
    catalog_id: str | None = None

    @property
    def qualified_name(self) -> str:
        return f"{self.namespace}:{self.name}"

    @property
    def approval_required(self) -> bool:
        return self.risk_level in APPROVAL_REQUIRED_RISKS or self.requires_approval is True

    def validate(self) -> None:
        if self.risk_level not in RISK_LEVELS:
            raise ValueError(f"invalid tool risk_level: {self.risk_level}")
        if not self.namespace.strip() or not self.name.strip():
            raise ValueError("tool namespace and name are required")
        if ":" in self.namespace or ":" in self.name:
            raise ValueError("tool namespace and name must not contain ':'")
        if not self.description.strip():
            raise ValueError("tool description is required")
        if self.catalog_id is not None and not self.catalog_id.strip():
            raise ValueError("tool catalog_id must be non-blank when provided")
        timeout_ms = cast(object, self.timeout_ms)
        if (
            not isinstance(timeout_ms, int)
            or isinstance(timeout_ms, bool)
            or not 1 <= timeout_ms <= 300_000
        ):
            raise ValueError("tool timeout_ms must be between 1 and 300000")
        validate_tool_schema(self.input_schema, label="input_schema", reject_reserved=True)
        validate_tool_schema(self.output_schema, label="output_schema", reject_reserved=False)


def validate_tool_schema(
    schema: Mapping[str, Any],
    *,
    label: str,
    reject_reserved: bool,
) -> None:
    if schema.get("type") != "object":
        raise ValueError(f"tool {label} must have type object")
    if "properties" in schema and not isinstance(schema.get("properties"), Mapping):
        raise ValueError(f"tool {label} properties must be an object")
    properties = cast(object, schema.get("properties", {}))
    if isinstance(properties, Mapping):
        for field_name, field_schema in cast(Mapping[object, object], properties).items():
            if not isinstance(field_name, str) or not isinstance(field_schema, Mapping):
                raise ValueError(f"tool {label} properties must define objects")
            if reject_reserved and field_name in RESERVED_LANGCHAIN_TOOL_ARGUMENTS:
                raise ValueError("tool input_schema uses reserved LangChain tool argument")
    if "required" in schema:
        required = cast(object, schema.get("required"))
        if not isinstance(required, list) or not all(
            isinstance(field_name, str) for field_name in cast(list[object], required)
        ):
            raise ValueError(f"tool {label} required must be string names")
        required_names = cast(list[str], required)
        if isinstance(properties, Mapping):
            property_names = set(cast(Mapping[object, object], properties))
            if any(field_name not in property_names for field_name in required_names):
                raise ValueError(f"tool {label} required fields must exist")
