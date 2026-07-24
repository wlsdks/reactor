from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from reactor.release.a2a_smoke import (
    A2AHttpResult,
    LiveA2APeerSmokeConfig,
    main,
    run_live_a2a_peer_smoke,
)


def test_live_a2a_peer_smoke_requires_task_api_for_passing_live_readiness() -> None:
    probe = FakeA2AHttpProbe(
        {
            "/.well-known/agent-card.json": A2AHttpResult(
                ok=True,
                status_code=200,
                body={
                    "name": "Reactor",
                    "supportedInterfaces": [
                        {
                            "protocolBinding": "JSONRPC",
                            "protocolVersion": "1.0",
                            "url": "https://reactor.example/a2a",
                        }
                    ],
                },
            ),
            "/v1/a2a/diagnostics": A2AHttpResult(
                ok=True,
                status_code=200,
                body={
                    "protocolVersion": "1.0",
                    "sdkAvailable": True,
                    "endpoint": "https://reactor.example/a2a",
                },
            ),
        }
    )

    report = run_live_a2a_peer_smoke(
        LiveA2APeerSmokeConfig(base_url="https://reactor.example"),
        http_probe=probe,
        environ={},
    )

    assert report == {
        "ok": False,
        "status": "skipped",
        "scope": "live",
        "base_url": "https://reactor.example",
        "error": "missing required A2A task API credentials",
        "evidence": {
            "artifact": "reports/live-peer-network-interoperability-smoke.json",
            "owner": "reactor.release",
            "mode": "live_a2a_peer_network_smoke",
            "a2aProtocol": {
                "status": "verified",
                "agentCard": {
                    "name": "Reactor",
                    "interfaceCount": 1,
                    "interfaceProtocolBindings": ["JSONRPC"],
                    "interfaceProtocolVersions": ["1.0"],
                    "interfaceUrls": ["https://reactor.example/a2a"],
                    "wellKnownPath": "/.well-known/agent-card.json",
                },
                "diagnostics": {
                    "sdkAvailable": True,
                    "protocolVersion": "1.0",
                    "endpoint": "https://reactor.example/a2a",
                    "path": "/v1/a2a/diagnostics",
                },
                "protocolNegotiation": {
                    "requestHeader": "A2A-Version",
                    "requestedVersion": "1.0",
                    "responseVersion": "1.0",
                    "majorMinorOnly": True,
                    "agentCardVersionsChecked": True,
                    "serverGeneratedTaskIds": True,
                    "sdkFastApiSurface": True,
                    "telemetryInstrumentation": "a2a-sdk[telemetry]",
                },
                "taskApi": {
                    "status": "skipped",
                    "reason": "REACTOR_A2A_API_KEY not configured",
                    "path": "/v1/a2a/tasks",
                },
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
                "secretFree": True,
                "tlsRequired": True,
            },
        },
        "checks": {
            "base_url": {"status": "passed"},
            "agent_card": {
                "status": "passed",
                "name": "Reactor",
                "interface_count": 1,
                "interface_protocol_bindings": ["JSONRPC"],
                "interface_protocol_versions": ["1.0"],
                "interface_urls": ["https://reactor.example/a2a"],
            },
            "diagnostics": {
                "status": "passed",
                "protocol_version": "1.0",
                "endpoint": "https://reactor.example/a2a",
            },
            "task_api": {
                "status": "skipped",
                "reason": "REACTOR_A2A_API_KEY not configured",
            },
        },
    }
    assert probe.get_paths == ["/.well-known/agent-card.json", "/v1/a2a/diagnostics"]


def test_live_a2a_peer_smoke_rejects_credential_bearing_base_url_without_echoing_it() -> None:
    credential = "-".join(("a2a", "credential", "value"))

    report = run_live_a2a_peer_smoke(
        LiveA2APeerSmokeConfig(
            base_url=f"https://reactor.example/a2a?access_token={credential}",
        ),
        http_probe=FakeA2AHttpProbe({}),
        environ={"REACTOR_A2A_API_KEY": credential},
    )

    assert report == {
        "ok": False,
        "status": "failed",
        "scope": "live",
        "checks": {"base_url": {"status": "failed", "reason": "secret_bearing_url"}},
        "error": "A2A base URL must not contain credentials",
    }
    assert credential not in json.dumps(report)


def test_live_a2a_peer_smoke_skips_when_base_url_is_missing() -> None:
    report = run_live_a2a_peer_smoke(
        LiveA2APeerSmokeConfig(base_url=""),
        http_probe=FakeA2AHttpProbe({}),
        environ={},
    )

    assert report == {
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


def test_live_a2a_peer_smoke_records_sanitized_task_api_failure() -> None:
    probe = FakeA2AHttpProbe(
        {
            "/.well-known/agent-card.json": A2AHttpResult(
                ok=True,
                status_code=200,
                body={"name": "Reactor", "supportedInterfaces": []},
            ),
            "/v1/a2a/diagnostics": A2AHttpResult(
                ok=True,
                status_code=200,
                body={"protocolVersion": "1.0", "sdkAvailable": True, "endpoint": "/a2a"},
            ),
            "/v1/a2a/tasks": A2AHttpResult(
                ok=False,
                status_code=403,
                error="denied for a2a-secret-key",
            ),
        }
    )

    report = run_live_a2a_peer_smoke(
        LiveA2APeerSmokeConfig(base_url="https://reactor.example"),
        http_probe=probe,
        environ={"REACTOR_A2A_API_KEY": "a2a-secret-key"},
    )

    assert report["ok"] is False
    assert report["status"] == "failed"
    assert report["checks"]["task_api"] == {
        "status": "failed",
        "status_code": 403,
        "error": "denied for [redacted]",
    }


def test_live_a2a_peer_smoke_marks_agent_card_urls_with_secrets_not_secret_free() -> None:
    probe = FakeA2AHttpProbe(
        {
            "/.well-known/agent-card.json": A2AHttpResult(
                ok=True,
                status_code=200,
                body={
                    "name": "Reactor",
                    "supportedInterfaces": [
                        {
                            "protocolBinding": "JSONRPC",
                            "protocolVersion": "1.0",
                            "url": "https://reactor.example/a2a?api_key=sk-test-secret",
                        }
                    ],
                },
            ),
            "/v1/a2a/diagnostics": A2AHttpResult(
                ok=True,
                status_code=200,
                body={
                    "protocolVersion": "1.0",
                    "sdkAvailable": True,
                    "endpoint": "https://reactor.example/a2a?api_key=sk-test-secret",
                },
            ),
            "/v1/a2a/tasks": A2AHttpResult(
                ok=True,
                status_code=200,
                body={"taskId": "task_1", "status": "submitted"},
            ),
        }
    )

    report = run_live_a2a_peer_smoke(
        LiveA2APeerSmokeConfig(base_url="https://reactor.example"),
        http_probe=probe,
        environ={"REACTOR_A2A_API_KEY": "test-api-key"},
    )

    evidence = report["evidence"]["a2aProtocol"]
    assert evidence["secretFree"] is False


def test_live_a2a_peer_smoke_marks_plain_http_a2a_urls_without_tls() -> None:
    probe = FakeA2AHttpProbe(
        {
            "/.well-known/agent-card.json": A2AHttpResult(
                ok=True,
                status_code=200,
                body={
                    "name": "Reactor",
                    "supportedInterfaces": [
                        {
                            "protocolBinding": "JSONRPC",
                            "protocolVersion": "1.0",
                            "url": "http://reactor.example/a2a",
                        }
                    ],
                },
            ),
            "/v1/a2a/diagnostics": A2AHttpResult(
                ok=True,
                status_code=200,
                body={
                    "protocolVersion": "1.0",
                    "sdkAvailable": True,
                    "endpoint": "http://reactor.example/a2a",
                },
            ),
            "/v1/a2a/tasks": A2AHttpResult(
                ok=True,
                status_code=200,
                body={"taskId": "task_1", "status": "submitted"},
            ),
        }
    )

    report = run_live_a2a_peer_smoke(
        LiveA2APeerSmokeConfig(base_url="http://reactor.example"),
        http_probe=probe,
        environ={"REACTOR_A2A_API_KEY": "test-api-key"},
    )

    evidence = report["evidence"]["a2aProtocol"]
    assert evidence["tlsRequired"] is False


def test_live_a2a_peer_smoke_sends_major_minor_protocol_header() -> None:
    probe = fake_http_a2a_probe()

    report = run_live_a2a_peer_smoke(
        LiveA2APeerSmokeConfig(base_url="https://reactor.example"),
        http_probe=probe,
        environ={"REACTOR_A2A_API_KEY": "test-api-key"},
    )

    assert report["ok"] is True
    assert probe.request_headers == [
        {"A2A-Version": "1.0"},
        {"A2A-Version": "1.0"},
        {"A2A-Version": "1.0", "X-Reactor-API-Key": "test-api-key"},
    ]


def test_live_a2a_peer_smoke_marks_patch_protocol_version_not_major_minor() -> None:
    probe = FakeA2AHttpProbe(
        {
            "/.well-known/agent-card.json": A2AHttpResult(
                ok=True,
                status_code=200,
                body={
                    "name": "Reactor",
                    "supportedInterfaces": [
                        {
                            "protocolBinding": "JSONRPC",
                            "protocolVersion": "1.0",
                            "url": "https://reactor.example/a2a",
                        }
                    ],
                },
            ),
            "/v1/a2a/diagnostics": A2AHttpResult(
                ok=True,
                status_code=200,
                body={
                    "protocolVersion": "1.0.0",
                    "sdkAvailable": True,
                    "endpoint": "https://reactor.example/a2a",
                },
            ),
            "/v1/a2a/tasks": A2AHttpResult(
                ok=True,
                status_code=200,
                body={"taskId": "task_1", "status": "submitted"},
            ),
        }
    )

    report = run_live_a2a_peer_smoke(
        LiveA2APeerSmokeConfig(base_url="https://reactor.example"),
        http_probe=probe,
        environ={"REACTOR_A2A_API_KEY": "test-api-key"},
    )

    evidence = report["evidence"]["a2aProtocol"]
    negotiation = evidence["protocolNegotiation"]
    assert negotiation["majorMinorOnly"] is False


def test_live_a2a_peer_smoke_cli_writes_report(tmp_path: Path, monkeypatch: Any) -> None:
    output_path = tmp_path / "reports" / "release" / "a2a-smoke.json"

    monkeypatch.setenv("REACTOR_A2A_BASE_URL", "https://reactor.example")
    monkeypatch.setenv("REACTOR_A2A_API_KEY", "test-api-key")
    monkeypatch.setattr("reactor.release.a2a_smoke.HttpA2AProbe", fake_http_a2a_probe)

    exit_code = main(["--output", str(output_path)])

    assert exit_code == 0
    assert json.loads(output_path.read_text(encoding="utf-8"))["ok"] is True


class FakeA2AHttpProbe:
    def __init__(self, results: dict[str, A2AHttpResult]) -> None:
        self._results = results
        self.get_paths: list[str] = []
        self.post_paths: list[str] = []
        self.request_headers: list[dict[str, str]] = []

    def get_json(self, path: str, headers: dict[str, str]) -> A2AHttpResult:
        self.get_paths.append(path)
        self.request_headers.append(headers)
        return self._results[path]

    def post_json(
        self,
        path: str,
        *,
        headers: dict[str, str],
        payload: dict[str, object],
    ) -> A2AHttpResult:
        del payload
        self.post_paths.append(path)
        self.request_headers.append(headers)
        return self._results[path]


def fake_http_a2a_probe(**_: object) -> FakeA2AHttpProbe:
    return FakeA2AHttpProbe(
        {
            "/.well-known/agent-card.json": A2AHttpResult(
                ok=True,
                status_code=200,
                body={"name": "Reactor", "supportedInterfaces": []},
            ),
            "/v1/a2a/diagnostics": A2AHttpResult(
                ok=True,
                status_code=200,
                body={"protocolVersion": "1.0", "sdkAvailable": True, "endpoint": "/a2a"},
            ),
            "/v1/a2a/tasks": A2AHttpResult(
                ok=True,
                status_code=200,
                body={"taskId": "task_1", "status": "submitted"},
            ),
        }
    )
