from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import timedelta
from importlib import import_module
from typing import Any, Protocol, cast

from reactor.mcp.registry import McpServerRegistration, McpToolSnapshot
from reactor.tools.catalog import ToolSpec

LANGCHAIN_MCP_TOOLS_MODULE = cast(Any, import_module("langchain_mcp_adapters.tools"))
LANGCHAIN_LOAD_MCP_TOOLS: Any = LANGCHAIN_MCP_TOOLS_MODULE.load_mcp_tools


class LangChainNamedTool(Protocol):
    name: str


def build_tool_snapshot_hash(snapshots: Sequence[McpToolSnapshot]) -> str:
    payload = [
        {
            "qualified_name": snapshot.qualified_name,
            "description": snapshot.description,
            "input_schema": dict(snapshot.input_schema),
            "output_schema": dict(snapshot.output_schema),
            "risk_level": snapshot.risk_level,
            "enabled": snapshot.enabled,
        }
        for snapshot in sorted(snapshots, key=lambda item: item.qualified_name)
    ]
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def sync_mcp_tools_to_specs(snapshots: Sequence[McpToolSnapshot]) -> list[ToolSpec]:
    specs = [snapshot.to_tool_spec() for snapshot in snapshots if snapshot.enabled]
    return sorted(specs, key=lambda spec: spec.qualified_name)


def langchain_mcp_connection(registration: McpServerRegistration) -> dict[str, object]:
    registration.validate()
    if registration.auth_type != "none":
        raise ValueError("MCP auth adapters require credential binding")
    timeout = timedelta(milliseconds=registration.timeout_ms)
    if registration.transport == "stdio":
        return {
            "transport": "stdio",
            "command": str(registration.command),
            "args": list(registration.args),
            "session_kwargs": {"read_timeout_seconds": timeout},
        }
    if registration.transport == "streamable_http":
        return {
            "transport": "streamable_http",
            "url": str(registration.url),
            "timeout": timeout,
        }
    raise ValueError(f"unsupported MCP transport: {registration.transport}")


async def load_langchain_mcp_tools(
    registrations: Sequence[McpServerRegistration],
    *,
    loader: Any = LANGCHAIN_LOAD_MCP_TOOLS,
) -> list[LangChainNamedTool]:
    tools: list[LangChainNamedTool] = []
    for registration in registrations:
        loaded = await loader(
            None,
            connection=langchain_mcp_connection(registration),
            server_name=registration.name,
            tool_name_prefix=False,
            handle_tool_errors=True,
        )
        tools.extend(
            qualify_loaded_mcp_tools(
                cast(Sequence[LangChainNamedTool], loaded),
                server_name=registration.name,
            )
        )
    return tools


def qualify_loaded_mcp_tools(
    tools: Sequence[LangChainNamedTool],
    *,
    server_name: str,
) -> list[LangChainNamedTool]:
    qualified: list[LangChainNamedTool] = []
    for tool in tools:
        raw_name = str(tool.name)
        if raw_name.startswith(f"{server_name}:"):
            qualified.append(tool)
            continue
        if ":" in raw_name:
            raise ValueError("unexpected MCP tool namespace")
        if raw_name.startswith(f"{server_name}_"):
            raw_name = raw_name.removeprefix(f"{server_name}_")
        tool.name = f"{server_name}:{raw_name}"
        qualified.append(tool)
    return qualified
