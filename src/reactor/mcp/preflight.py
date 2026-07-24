from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from urllib.parse import urlparse

from reactor.mcp.registry import MCP_PROTOCOL_VERSION, McpServerRegistration

FORBIDDEN_AUTH_TYPES = {"provider_token_passthrough", "user_token_passthrough"}


@dataclass(frozen=True)
class McpPreflightPolicy:
    allow_private_addresses: bool = False
    negotiated_protocol_version: str = MCP_PROTOCOL_VERSION
    credential_binding_available: bool = False


@dataclass(frozen=True)
class McpPreflightResult:
    ok: bool
    status: str
    error_code: str | None = None
    detail: str = "ok"


def preflight_mcp_server(
    registration: McpServerRegistration,
    policy: McpPreflightPolicy,
) -> McpPreflightResult:
    try:
        registration.validate()
    except ValueError as exc:
        return McpPreflightResult(
            ok=False,
            status="degraded",
            error_code="invalid_registration",
            detail=str(exc),
        )

    if registration.auth_type in FORBIDDEN_AUTH_TYPES:
        return McpPreflightResult(
            ok=False,
            status="degraded",
            error_code="token_passthrough_forbidden",
            detail="MCP servers must use scoped server credentials, not provider/user tokens",
        )

    if registration.auth_type != "none" and not policy.credential_binding_available:
        return McpPreflightResult(
            ok=False,
            status="degraded",
            error_code="credential_binding_required",
            detail="authenticated MCP servers require scoped credential binding",
        )

    if registration.transport == "streamable_http" and registration.auth_type != "none":
        parsed_url = urlparse(registration.url or "")
        if parsed_url.scheme != "https":
            return McpPreflightResult(
                ok=False,
                status="degraded",
                error_code="tls_required",
                detail="authenticated Streamable HTTP MCP servers require HTTPS",
            )

    if policy.negotiated_protocol_version != MCP_PROTOCOL_VERSION:
        return McpPreflightResult(
            ok=False,
            status="degraded",
            error_code="unsupported_protocol_version",
            detail=f"expected {MCP_PROTOCOL_VERSION}, got {policy.negotiated_protocol_version}",
        )

    if registration.transport == "streamable_http" and not policy.allow_private_addresses:
        if registration.url is not None and url_targets_private_address(registration.url):
            return McpPreflightResult(
                ok=False,
                status="degraded",
                error_code="private_address_blocked",
                detail="private and link-local MCP targets are blocked by policy",
            )

    return McpPreflightResult(ok=True, status="registered")


def url_targets_private_address(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.hostname
    if host is None:
        return True
    if host in {"localhost", "localhost.localdomain"}:
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )
