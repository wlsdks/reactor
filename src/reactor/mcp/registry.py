from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from reactor.tools.catalog import ToolSpec

MCP_PROTOCOL_VERSION = "2025-11-25"
MCP_TRANSPORTS = {"stdio", "streamable_http"}
MCP_SERVER_STATUSES = {"registered", "healthy", "degraded", "disabled"}


def empty_reconnect_policy() -> dict[str, Any]:
    return {}


@dataclass(frozen=True)
class McpServerRegistration:
    tenant_id: str
    name: str
    transport: str
    command: str | None = None
    args: Sequence[str] = field(default_factory=tuple)
    url: str | None = None
    auth_type: str = "none"
    timeout_ms: int = 15_000
    reconnect_policy: Mapping[str, Any] = field(default_factory=empty_reconnect_policy)

    def validate(self) -> None:
        if not self.tenant_id.strip():
            raise ValueError("tenant_id is required")
        if not self.name.strip() or ":" in self.name:
            raise ValueError("MCP server name is required and must not contain ':'")
        if self.transport not in MCP_TRANSPORTS:
            raise ValueError(f"unsupported MCP transport: {self.transport}")
        if self.transport == "stdio" and not (self.command and self.command.strip()):
            raise ValueError("stdio MCP servers require command")
        if self.transport == "streamable_http" and not (self.url and self.url.strip()):
            raise ValueError("streamable_http MCP servers require url")
        if self.timeout_ms <= 0:
            raise ValueError("timeout_ms must be positive")


@dataclass(frozen=True)
class McpToolSnapshot:
    tenant_id: str
    server_name: str
    tool_name: str
    description: str
    input_schema: Mapping[str, Any]
    output_schema: Mapping[str, Any]
    risk_level: str = "read"
    enabled: bool = True
    snapshot_hash: str = "manual"

    @property
    def qualified_name(self) -> str:
        return f"{self.server_name}:{self.tool_name}"

    def to_tool_spec(self) -> ToolSpec:
        spec = ToolSpec(
            tenant_id=self.tenant_id,
            namespace=self.server_name,
            name=self.tool_name,
            description=self.description,
            risk_level=self.risk_level,
            input_schema=self.input_schema,
            output_schema=self.output_schema,
            enabled=self.enabled,
        )
        spec.validate()
        return spec
