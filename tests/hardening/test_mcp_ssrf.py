from __future__ import annotations

from reactor.mcp.preflight import McpPreflightPolicy, preflight_mcp_server
from reactor.mcp.registry import McpServerRegistration


def test_mcp_preflight_blocks_link_local_metadata_service() -> None:
    registration = McpServerRegistration(
        tenant_id="tenant_1",
        name="metadata",
        transport="streamable_http",
        url="http://169.254.169.254/latest/meta-data",
    )

    result = preflight_mcp_server(registration, McpPreflightPolicy())

    assert result.ok is False
    assert result.error_code == "private_address_blocked"
