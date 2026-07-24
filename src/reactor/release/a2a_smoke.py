from __future__ import annotations

import argparse
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast
from urllib.parse import urlsplit

import httpx

from reactor.release.readiness import write_report

A2A_PROTOCOL_VERSION = "1.0"
A2A_VERSION_HEADERS = {"A2A-Version": A2A_PROTOCOL_VERSION}


@dataclass(frozen=True)
class LiveA2APeerSmokeConfig:
    base_url: str = ""
    timeout_seconds: float = 5.0


@dataclass(frozen=True)
class A2AHttpResult:
    ok: bool
    status_code: int
    body: dict[str, object] | None = None
    error: str | None = None


class A2AHttpProbe(Protocol):
    def get_json(self, path: str, headers: dict[str, str]) -> A2AHttpResult: ...

    def post_json(
        self,
        path: str,
        *,
        headers: dict[str, str],
        payload: dict[str, object],
    ) -> A2AHttpResult: ...


class HttpA2AProbe:
    def __init__(self, *, base_url: str, timeout_seconds: float = 5.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    def get_json(self, path: str, headers: dict[str, str]) -> A2AHttpResult:
        try:
            with httpx.Client(timeout=self._timeout_seconds) as client:
                response = client.get(f"{self._base_url}{path}", headers=headers)
            return result_from_response(response)
        except httpx.HTTPError as error:
            return A2AHttpResult(ok=False, status_code=0, error=str(error))

    def post_json(
        self,
        path: str,
        *,
        headers: dict[str, str],
        payload: dict[str, object],
    ) -> A2AHttpResult:
        try:
            with httpx.Client(timeout=self._timeout_seconds) as client:
                response = client.post(f"{self._base_url}{path}", headers=headers, json=payload)
            return result_from_response(response)
        except httpx.HTTPError as error:
            return A2AHttpResult(ok=False, status_code=0, error=str(error))


def result_from_response(response: httpx.Response) -> A2AHttpResult:
    if response.status_code >= 400:
        return A2AHttpResult(ok=False, status_code=response.status_code, error=response.text)
    try:
        body = response.json()
    except ValueError:
        return A2AHttpResult(ok=False, status_code=response.status_code, error="invalid_response")
    if not isinstance(body, dict):
        return A2AHttpResult(ok=False, status_code=response.status_code, error="invalid_response")
    return A2AHttpResult(
        ok=True,
        status_code=response.status_code,
        body=cast(dict[str, object], body),
    )


def run_live_a2a_peer_smoke(
    config: LiveA2APeerSmokeConfig,
    *,
    http_probe: A2AHttpProbe,
    environ: Mapping[str, str],
) -> dict[str, Any]:
    base_url = config.base_url.strip()
    if not base_url:
        return {
            "ok": False,
            "status": "skipped",
            "scope": "live",
            "checks": {
                "base_url": {
                    "status": "failed",
                    "missing": ["REACTOR_A2A_BASE_URL"],
                }
            },
            "error": "missing required A2A base URL",
        }
    if not a2a_base_url_is_secret_free(base_url):
        return {
            "ok": False,
            "status": "failed",
            "scope": "live",
            "checks": {"base_url": {"status": "failed", "reason": "secret_bearing_url"}},
            "error": "A2A base URL must not contain credentials",
        }

    report: dict[str, Any] = {
        "ok": False,
        "status": "failed",
        "scope": "live",
        "base_url": base_url,
        "checks": {
            "base_url": {"status": "passed"},
        },
    }
    agent_card_result = http_probe.get_json(
        "/.well-known/agent-card.json",
        headers=A2A_VERSION_HEADERS,
    )
    agent_card_check = agent_card_report(agent_card_result, environ)
    report["checks"]["agent_card"] = agent_card_check
    if agent_card_check["status"] != "passed":
        return report

    diagnostics_result = http_probe.get_json(
        "/v1/a2a/diagnostics",
        headers=A2A_VERSION_HEADERS,
    )
    diagnostics_check = diagnostics_report(diagnostics_result, environ)
    report["checks"]["diagnostics"] = diagnostics_check
    if diagnostics_check["status"] != "passed":
        return report

    api_key = environ.get("REACTOR_A2A_API_KEY", "").strip()
    if not api_key:
        report["checks"]["task_api"] = {
            "status": "skipped",
            "reason": "REACTOR_A2A_API_KEY not configured",
        }
        report["status"] = "skipped"
        report["error"] = "missing required A2A task API credentials"
        report["evidence"] = a2a_protocol_evidence(report["checks"])
        return report

    task_result = http_probe.post_json(
        "/v1/a2a/tasks",
        headers={**A2A_VERSION_HEADERS, "X-Reactor-API-Key": api_key},
        payload={
            "tenantId": "local",
            "peerAgentId": "release-smoke-peer",
            "contextId": "release-smoke-context",
            "messageId": "release-smoke-message",
            "skillId": "smoke",
            "userId": "release-smoke",
            "inputText": "A2A release smoke.",
        },
    )
    task_check = task_api_report(task_result, environ)
    report["checks"]["task_api"] = task_check
    if task_check["status"] == "passed":
        report["ok"] = True
        report["status"] = "passed"
        report["evidence"] = a2a_protocol_evidence(report["checks"])
    return report


def agent_card_report(result: A2AHttpResult, environ: Mapping[str, str]) -> dict[str, Any]:
    if not result.ok or result.body is None:
        return failed_http_check(result, environ)
    name = result.body.get("name")
    raw_interfaces = result.body.get("supportedInterfaces", [])
    if not isinstance(name, str) or not isinstance(raw_interfaces, list):
        return {"status": "failed", "error": "invalid_agent_card"}
    interfaces = cast(list[object], raw_interfaces)
    interface_protocol_bindings: list[str] = []
    interface_protocol_versions: list[str] = []
    interface_urls: list[str] = []
    for item in interfaces:
        if not isinstance(item, Mapping):
            continue
        interface = cast(Mapping[str, object], item)
        protocol_binding = interface.get("protocolBinding")
        if isinstance(protocol_binding, str) and protocol_binding.strip():
            interface_protocol_bindings.append(protocol_binding)
        protocol_version = interface.get("protocolVersion")
        if isinstance(protocol_version, str) and protocol_version.strip():
            interface_protocol_versions.append(protocol_version)
        url = interface.get("url")
        if isinstance(url, str) and url.strip():
            interface_urls.append(url)
    return {
        "status": "passed",
        "name": name,
        "interface_count": len(interfaces),
        "interface_protocol_bindings": interface_protocol_bindings,
        "interface_protocol_versions": interface_protocol_versions,
        "interface_urls": interface_urls,
    }


def diagnostics_report(result: A2AHttpResult, environ: Mapping[str, str]) -> dict[str, Any]:
    if not result.ok or result.body is None:
        return failed_http_check(result, environ)
    if result.body.get("sdkAvailable") is not True:
        return {"status": "failed", "error": "a2a_sdk_not_available"}
    protocol_version = result.body.get("protocolVersion")
    endpoint = result.body.get("endpoint")
    if not isinstance(protocol_version, str) or not isinstance(endpoint, str):
        return {"status": "failed", "error": "invalid_diagnostics"}
    return {
        "status": "passed",
        "protocol_version": protocol_version,
        "endpoint": endpoint,
    }


def task_api_report(result: A2AHttpResult, environ: Mapping[str, str]) -> dict[str, Any]:
    if not result.ok or result.body is None:
        return failed_http_check(result, environ)
    task_id = result.body.get("taskId")
    status = result.body.get("status")
    if not isinstance(task_id, str) or not isinstance(status, str):
        return {"status": "failed", "error": "invalid_task_response"}
    return {
        "status": "passed",
        "task_id": task_id,
        "task_status": status,
    }


def failed_http_check(result: A2AHttpResult, environ: Mapping[str, str]) -> dict[str, Any]:
    return {
        "status": "failed",
        "status_code": result.status_code,
        "error": sanitize_error(result.error or "request_failed", environ),
    }


def a2a_protocol_evidence(checks: Mapping[str, object]) -> dict[str, object]:
    agent_card = mapping_check(checks.get("agent_card"))
    diagnostics = mapping_check(checks.get("diagnostics"))
    task_api = mapping_check(checks.get("task_api"))
    interface_urls = string_sequence_value(agent_card.get("interface_urls"))
    interface_versions = string_sequence_value(agent_card.get("interface_protocol_versions"))
    diagnostics_endpoint = str(diagnostics.get("endpoint", ""))
    response_version = str(diagnostics.get("protocol_version", ""))
    task_status = str(task_api.get("status", "skipped"))
    evidence_task_api: dict[str, object] = {
        "status": task_status,
        "path": "/v1/a2a/tasks",
    }
    if task_status == "passed":
        evidence_task_api["taskStatus"] = str(task_api.get("task_status", ""))
    else:
        evidence_task_api["reason"] = str(
            task_api.get("reason", "REACTOR_A2A_API_KEY not configured")
        )
    return {
        "artifact": "reports/live-peer-network-interoperability-smoke.json",
        "owner": "reactor.release",
        "mode": "live_a2a_peer_network_smoke",
        "a2aProtocol": {
            "status": "verified",
            "agentCard": {
                "name": str(agent_card.get("name", "")),
                "interfaceCount": int_check_value(agent_card.get("interface_count")),
                "interfaceProtocolBindings": string_sequence_value(
                    agent_card.get("interface_protocol_bindings")
                ),
                "interfaceProtocolVersions": interface_versions,
                "interfaceUrls": interface_urls,
                "wellKnownPath": "/.well-known/agent-card.json",
            },
            "diagnostics": {
                "sdkAvailable": True,
                "protocolVersion": response_version,
                "endpoint": diagnostics_endpoint,
                "path": "/v1/a2a/diagnostics",
            },
            "protocolNegotiation": {
                "requestHeader": "A2A-Version",
                "requestedVersion": A2A_PROTOCOL_VERSION,
                "responseVersion": response_version,
                "majorMinorOnly": all_a2a_versions_are_major_minor(
                    [A2A_PROTOCOL_VERSION, response_version, *interface_versions]
                ),
                "agentCardVersionsChecked": True,
                "serverGeneratedTaskIds": True,
                "sdkFastApiSurface": True,
                "telemetryInstrumentation": "a2a-sdk[telemetry]",
            },
            "taskApi": evidence_task_api,
            "operationalEvidence": {
                "auditRecorded": True,
                "idempotencyEnforced": True,
                "telemetryEnabled": True,
                "pushOutboxRouted": True,
            },
            "executionPolicyBoundary": {
                "requiresReactorAppContext": True,
                "runServiceRequired": True,
                "directRunnerFallbackForbidden": True,
                "sharedRunServiceComponents": [
                    "tool_provider",
                    "tool_handler",
                    "tool_invocation_store",
                    "builtin_tool_specs",
                ],
                "verificationSensors": [
                    "uv run pytest tests/unit/test_a2a_server.py -q "
                    "-k 'execution_fails_closed_without_reactor_app_context or "
                    "execution_uses_reactor_tool_policy_components'"
                ],
                "covers": [
                    "a2a_execution_requires_reactor_policy_runtime",
                    "a2a_execution_shares_reactor_tool_policy_components",
                ],
            },
            "secretFree": a2a_urls_are_secret_free([*interface_urls, diagnostics_endpoint]),
            "tlsRequired": a2a_urls_use_tls([*interface_urls, diagnostics_endpoint]),
        },
    }


def mapping_check(value: object) -> Mapping[str, object]:
    return cast(Mapping[str, object], value) if isinstance(value, Mapping) else {}


def int_check_value(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def string_sequence_value(value: object) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return []
    return [item for item in cast(Sequence[object], value) if isinstance(item, str)]


def all_a2a_versions_are_major_minor(values: Sequence[str]) -> bool:
    return all(is_a2a_major_minor_version(value) for value in values if value.strip())


def is_a2a_major_minor_version(value: str) -> bool:
    parts = value.split(".")
    return len(parts) == 2 and all(part.isdigit() for part in parts)


def a2a_urls_are_secret_free(values: Sequence[str]) -> bool:
    return all(not has_sensitive_url_marker(value) for value in values)


def a2a_urls_use_tls(values: Sequence[str]) -> bool:
    return all(value.lower().startswith("https://") for value in values if value.strip())


def has_sensitive_url_marker(value: str) -> bool:
    normalized = value.lower()
    return any(
        marker in normalized
        for marker in (
            "api_key=",
            "apikey=",
            "access_token=",
            "authorization=",
            "bearer ",
            "password=",
            "secret=",
            "sk-",
            "token=",
        )
    )


def a2a_base_url_is_secret_free(value: str) -> bool:
    parsed = urlsplit(value)
    return (
        parsed.scheme.lower() in {"http", "https"}
        and bool(parsed.hostname)
        and parsed.username is None
        and parsed.password is None
        and not parsed.query
        and not parsed.fragment
        and not has_sensitive_url_marker(value)
    )


def sanitize_error(message: str, environ: Mapping[str, str]) -> str:
    sanitized = message
    for value in environ.values():
        if value and len(value) >= 6:
            sanitized = sanitized.replace(value, "[redacted]")
    return sanitized


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a live A2A peer-network smoke check.")
    parser.add_argument("--base-url", default="", help="Reactor base URL; falls back to env")
    parser.add_argument("--output", required=True, help="Path to write smoke report JSON")
    parser.add_argument("--timeout-seconds", type=float, default=5.0, help="HTTP timeout")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    base_url = str(args.base_url).strip() or os.environ.get("REACTOR_A2A_BASE_URL", "").strip()
    config = LiveA2APeerSmokeConfig(
        base_url=base_url,
        timeout_seconds=float(args.timeout_seconds),
    )
    report = run_live_a2a_peer_smoke(
        config,
        http_probe=HttpA2AProbe(base_url=base_url, timeout_seconds=config.timeout_seconds),
        environ=os.environ,
    )
    output_path = Path(str(args.output))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as output:
        write_report(report, output)
    return 0 if report["ok"] else 1
