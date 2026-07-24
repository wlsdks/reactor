from __future__ import annotations

import hmac
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, cast
from urllib.parse import urlparse

ADMIN_PREFLIGHT_PATH = "/admin/preflight"


@dataclass(frozen=True)
class McpAdminPreflightConfig:
    base_url: str
    token: str | None
    hmac_secret: str | None
    hmac_required: bool
    timeout_ms: int
    connect_timeout_ms: int


def preflight_config_from_server(server: Any) -> McpAdminPreflightConfig | str:
    base_url = resolve_admin_base_url(getattr(server, "url", None))
    if base_url is None:
        return (
            f"MCP server '{getattr(server, 'name', 'unknown')}' has invalid admin URL. "
            "Set absolute url with http/https"
        )
    reconnect_policy = getattr(server, "reconnect_policy", {})
    empty_policy: Mapping[str, Any] = {}
    policy = (
        cast(Mapping[str, Any], reconnect_policy)
        if isinstance(reconnect_policy, Mapping)
        else empty_policy
    )
    token = optional_str(policy.get("adminToken") or policy.get("admin_token"))
    hmac_secret = optional_str(policy.get("adminHmacSecret") or policy.get("admin_hmac_secret"))
    hmac_required = bool(policy.get("adminHmacRequired") or policy.get("admin_hmac_required"))
    timeout_ms = positive_int(policy.get("adminTimeoutMs"), getattr(server, "timeout_ms", 15_000))
    connect_timeout_ms = positive_int(policy.get("adminConnectTimeoutMs"), min(timeout_ms, 5_000))
    return McpAdminPreflightConfig(
        base_url=base_url,
        token=token,
        hmac_secret=hmac_secret,
        hmac_required=hmac_required,
        timeout_ms=timeout_ms,
        connect_timeout_ms=connect_timeout_ms,
    )


def resolve_admin_base_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    path = parsed.path.rstrip("/")
    if path.endswith("/sse"):
        path = path.removesuffix("/sse")
    if path.endswith("/mcp"):
        path = path.removesuffix("/mcp")
    return parsed._replace(path=path, params="", query="", fragment="").geturl().rstrip("/")


def admin_preflight_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}{ADMIN_PREFLIGHT_PATH}"


def preflight_hmac_signature(
    *,
    secret: str,
    method: str,
    path: str,
    query: str,
    body: str,
    timestamp: str,
) -> str:
    body_hash = sha256(body.encode()).hexdigest()
    canonical = "\n".join([method.upper(), path, query, timestamp, body_hash])
    return hmac.new(secret.encode(), canonical.encode(), sha256).hexdigest()


def optional_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def positive_int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str) and value.strip().isdigit():
        parsed = int(value.strip())
        return parsed if parsed > 0 else default
    return default
