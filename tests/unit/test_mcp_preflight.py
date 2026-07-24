from __future__ import annotations

from reactor.mcp.preflight import McpPreflightPolicy, preflight_mcp_server
from reactor.mcp.registry import McpServerRegistration


def test_mcp_preflight_rejects_private_http_target_by_default() -> None:
    registration = McpServerRegistration(
        tenant_id="tenant_1",
        name="local",
        transport="streamable_http",
        url="http://127.0.0.1:9000/mcp",
    )

    result = preflight_mcp_server(registration, McpPreflightPolicy())

    assert result.ok is False
    assert result.status == "degraded"
    assert result.error_code == "private_address_blocked"


def test_mcp_preflight_allows_private_http_target_with_admin_policy() -> None:
    registration = McpServerRegistration(
        tenant_id="tenant_1",
        name="local",
        transport="streamable_http",
        url="http://127.0.0.1:9000/mcp",
    )

    result = preflight_mcp_server(
        registration,
        McpPreflightPolicy(allow_private_addresses=True),
    )

    assert result.ok is True
    assert result.status == "registered"


def test_mcp_preflight_rejects_token_passthrough_auth() -> None:
    registration = McpServerRegistration(
        tenant_id="tenant_1",
        name="remote",
        transport="streamable_http",
        url="https://mcp.example.com/mcp",
        auth_type="provider_token_passthrough",
    )

    result = preflight_mcp_server(registration, McpPreflightPolicy())

    assert result.ok is False
    assert result.error_code == "token_passthrough_forbidden"


def test_mcp_preflight_rejects_auth_without_credential_binding() -> None:
    registration = McpServerRegistration(
        tenant_id="tenant_1",
        name="remote",
        transport="streamable_http",
        url="https://mcp.example.com/mcp",
        auth_type="bearer",
    )

    result = preflight_mcp_server(registration, McpPreflightPolicy())

    assert result.ok is False
    assert result.status == "degraded"
    assert result.error_code == "credential_binding_required"


def test_mcp_preflight_allows_auth_with_credential_binding() -> None:
    registration = McpServerRegistration(
        tenant_id="tenant_1",
        name="remote",
        transport="streamable_http",
        url="https://mcp.example.com/mcp",
        auth_type="bearer",
    )

    result = preflight_mcp_server(
        registration,
        McpPreflightPolicy(credential_binding_available=True),
    )

    assert result.ok is True
    assert result.status == "registered"


def test_mcp_preflight_rejects_authenticated_http_without_tls() -> None:
    registration = McpServerRegistration(
        tenant_id="tenant_1",
        name="remote",
        transport="streamable_http",
        url="http://mcp.example.com/mcp",
        auth_type="bearer",
    )

    result = preflight_mcp_server(
        registration,
        McpPreflightPolicy(credential_binding_available=True),
    )

    assert result.ok is False
    assert result.status == "degraded"
    assert result.error_code == "tls_required"


def test_mcp_preflight_marks_unsupported_protocol_degraded() -> None:
    registration = McpServerRegistration(
        tenant_id="tenant_1",
        name="remote",
        transport="streamable_http",
        url="https://mcp.example.com/mcp",
    )

    result = preflight_mcp_server(
        registration,
        McpPreflightPolicy(negotiated_protocol_version="2024-11-05"),
    )

    assert result.ok is False
    assert result.error_code == "unsupported_protocol_version"
