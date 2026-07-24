from __future__ import annotations

import pytest

from reactor.mcp.registry import MCP_PROTOCOL_VERSION, McpServerRegistration, McpToolSnapshot


def test_mcp_protocol_version_matches_spec_target() -> None:
    assert MCP_PROTOCOL_VERSION == "2025-11-25"


def test_stdio_server_requires_command() -> None:
    registration = McpServerRegistration(
        tenant_id="tenant_1",
        name="filesystem",
        transport="stdio",
    )

    with pytest.raises(ValueError, match="require command"):
        registration.validate()


def test_mcp_tool_snapshot_uses_server_qualified_tool_name() -> None:
    snapshot = McpToolSnapshot(
        tenant_id="tenant_1",
        server_name="SearchServer",
        tool_name="search_docs",
        description="Search approved documents.",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
    )

    spec = snapshot.to_tool_spec()

    assert snapshot.qualified_name == "SearchServer:search_docs"
    assert spec.qualified_name == "SearchServer:search_docs"
    assert spec.approval_required is False
