from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from reactor.observability.tracing import TracingConfigurationResult
from reactor.release.observability_smoke import (
    ObservabilitySmokeConfig,
    main,
    observability_smoke_diagnostics,
    observability_smoke_evidence,
    run_observability_smoke,
)


def test_observability_smoke_configures_langsmith_without_exposing_secrets() -> None:
    report = run_observability_smoke(
        ObservabilitySmokeConfig(
            trace_exporter="langsmith",
            langsmith_project="reactor-smoke",
            langsmith_endpoint="https://api.smith.langchain.com",
        ),
        environ={"LANGSMITH_API_KEY": "langsmith-key"},
        tracing_configurator=fake_tracing_configurator,
    )

    assert report == {
        "ok": True,
        "status": "passed",
        "scope": "local_contract",
        "evidence": {
            "artifact": "reports/observability-smoke.json",
            "command": (
                "uv run reactor-observability-smoke --output reports/observability-smoke.json"
            ),
            "owner": "reactor.observability",
            "mode": "langsmith_online_observability_contract",
            "observabilitySdk": {
                "status": "verified",
                "langsmith": {
                    "sdk": "langsmith",
                    "traceProvider": "langsmith",
                    "tracingEnv": "LANGSMITH_TRACING",
                    "projectEnv": "LANGSMITH_PROJECT",
                    "privacyEnv": [
                        "LANGSMITH_HIDE_INPUTS",
                        "LANGSMITH_HIDE_OUTPUTS",
                        "LANGSMITH_HIDE_METADATA",
                    ],
                },
                "opentelemetry": {
                    "sdk": "opentelemetry-sdk",
                    "tracerProvider": "TracerProvider",
                    "spanProcessor": "BatchSpanProcessor",
                    "exporters": ["ConsoleSpanExporter", "OTLPSpanExporter"],
                    "otlpProtocol": "http/protobuf",
                    "resourceAttributes": ["service.name", "deployment.environment"],
                    "sampler": "TraceIdRatioBased",
                    "providerShutdownOnLifespanExit": True,
                    "forceFlushBeforeShutdown": True,
                },
            },
            "observabilityTarget": {
                "traceProvider": "langsmith",
                "project": "reactor-smoke",
                "endpoint": "https://api.smith.langchain.com",
                "spanName": "reactor.release.observability_smoke",
                "secretFree": True,
            },
            "privacy": {
                "traceProvider": "langsmith",
                "hideInputs": True,
                "hideOutputs": True,
                "hideMetadata": True,
                "redactionCheck": "required",
                "redactionCoverage": [
                    "reactor.api_key",
                    "reactor.payload.password",
                    "reactor.payload.query",
                    "reactor.payload.actor_email",
                    "reactor.metadata.user_email",
                    "reactor.metadata.nested.authorization",
                ],
                "failureLogCoverage": {
                    "alertDispatchFailureFailsOpen": True,
                    "exceptionDetailsExcluded": True,
                    "safeIdentityFields": ["alert_id", "rule_id"],
                    "verificationSensor": (
                        "uv run pytest tests/unit/test_slo_alerts.py -q -k "
                        "keeps_alert_and_logs_safely_when_dispatch_fails"
                    ),
                },
            },
            "feedbackLoop": {
                "onlineSignal": "langsmith_traces_and_feedback",
                "offlineGate": "langsmith_eval_dataset_sync",
                "sourceSuite": "evals/agent-hardening.json",
                "promotionRule": "online_findings_become_offline_eval_cases",
                "promotedCaseIds": [
                    "tool-exposure-issue-readonly",
                    "rag-poisoning-retrieval-is-labeled",
                ],
            },
        },
        "checks": {
            "required_env": {
                "status": "passed",
                "exporter": "langsmith",
                "any_of": [["LANGSMITH_API_KEY", "REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"]],
            },
            "tracing_config": {
                "status": "passed",
                "exporter": "langsmith",
                "endpoint": "https://api.smith.langchain.com",
                "project": "reactor-smoke",
                "hide_inputs": True,
                "hide_outputs": True,
                "hide_metadata": True,
            },
            "redaction": {
                "status": "passed",
                "checkedFields": [
                    "reactor.api_key",
                    "reactor.payload.password",
                    "reactor.payload.query",
                    "reactor.payload.actor_email",
                    "reactor.metadata.user_email",
                    "reactor.metadata.nested.authorization",
                ],
                "secret_redacted": True,
                "payload_redacted": True,
                "metadata_redacted": True,
                "pii_redacted": True,
            },
            "span": {
                "status": "passed",
                "name": "reactor.release.observability_smoke",
            },
        },
    }
    assert "langsmith-key" not in json.dumps(report)
    assert "sample-user@example.com" not in json.dumps(report)


def test_observability_smoke_evidence_coverage_is_not_mutable_across_reports() -> None:
    first_evidence = observability_smoke_evidence()
    first_privacy = cast(dict[str, object], first_evidence["privacy"])
    first_coverage = cast(list[str], first_privacy["redactionCoverage"])
    first_coverage.clear()

    second_evidence = observability_smoke_evidence()
    second_privacy = cast(dict[str, object], second_evidence["privacy"])

    assert second_privacy["redactionCoverage"] == [
        "reactor.api_key",
        "reactor.payload.password",
        "reactor.payload.query",
        "reactor.payload.actor_email",
        "reactor.metadata.user_email",
        "reactor.metadata.nested.authorization",
    ]


def test_observability_smoke_skips_langsmith_when_key_is_missing() -> None:
    report = run_observability_smoke(
        ObservabilitySmokeConfig(trace_exporter="langsmith"),
        environ={},
        tracing_configurator=fake_tracing_configurator,
    )

    assert report["ok"] is False
    assert report["status"] == "skipped"
    assert report["checks"]["required_env"]["missing"] == [
        "LANGSMITH_API_KEY or REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"
    ]


def test_observability_smoke_diagnostics_reports_target_without_side_effects() -> None:
    report = observability_smoke_diagnostics(
        config=ObservabilitySmokeConfig(
            trace_exporter="langsmith",
            langsmith_project="reactor-prod",
            langsmith_endpoint="https://api.smith.langchain.com",
        ),
        environ={},
    )

    assert report["ok"] is False
    assert report["status"] == "skipped"
    assert report["scope"] == "local_contract_diagnostics"
    assert report["releaseGate"] == {
        "status": "blocked",
        "blocksReleaseReadiness": True,
        "reason": "missing_required_env",
        "requiredReport": "observability_smoke",
        "remediation": [
            "set_LANGSMITH_API_KEY_or_REACTOR_OBSERVABILITY_LANGSMITH_API_KEY",
            "run_reactor_observability_smoke",
            "include_passed_observability_smoke_report_in_release_readiness",
        ],
    }
    assert report["evidence"]["observabilityTarget"]["project"] == "reactor-prod"
    assert report["evidence"]["observabilityTarget"]["secretFree"] is True
    assert report["checks"]["required_env"]["status"] == "failed"

    ready_report = observability_smoke_diagnostics(
        config=ObservabilitySmokeConfig(trace_exporter="langsmith"),
        environ={"LANGSMITH_API_KEY": "langsmith-key"},
    )

    assert ready_report["releaseGate"] == {
        "status": "ready",
        "blocksReleaseReadiness": False,
        "reason": None,
        "requiredReport": "observability_smoke",
        "remediation": [],
    }


def test_observability_smoke_cli_writes_report(tmp_path: Path, monkeypatch: Any) -> None:
    output_path = tmp_path / "reports" / "release" / "observability-smoke.json"
    monkeypatch.setenv("LANGSMITH_API_KEY", "langsmith-key")
    monkeypatch.setattr(
        "reactor.release.observability_smoke.configure_tracing",
        fake_tracing_configurator,
    )

    exit_code = main(
        [
            "--output",
            str(output_path),
            "--langsmith-project",
            "reactor-smoke",
        ]
    )

    assert exit_code == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["evidence"]["artifact"] == "reports/observability-smoke.json"
    assert payload["evidence"]["owner"] == "reactor.observability"
    assert payload["checks"]["tracing_config"]["project"] == "reactor-smoke"


def fake_tracing_configurator(_: object) -> TracingConfigurationResult:
    return TracingConfigurationResult(
        enabled=True,
        exporter="langsmith",
        endpoint="https://api.smith.langchain.com",
    )
