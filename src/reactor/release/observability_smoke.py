from __future__ import annotations

import argparse
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from reactor.core.settings import Settings
from reactor.observability.tracing import (
    REDACTED,
    TracingConfigurationResult,
    clean_span_attributes,
    configure_tracing,
    normalize_trace_exporter,
    trace_reactor_span,
)
from reactor.release.backend_provider_smoke import LANGSMITH_KEY_ENV_NAMES
from reactor.release.provider_smoke import sanitize_error
from reactor.release.readiness import write_report


@dataclass(frozen=True)
class ObservabilitySmokeConfig:
    trace_exporter: str = "langsmith"
    langsmith_project: str = "reactor-observability-smoke"
    langsmith_endpoint: str = "https://api.smith.langchain.com"


REDACTION_COVERAGE_FIELDS = (
    "reactor.api_key",
    "reactor.payload.password",
    "reactor.payload.query",
    "reactor.payload.actor_email",
    "reactor.metadata.user_email",
    "reactor.metadata.nested.authorization",
)


def run_observability_smoke(
    config: ObservabilitySmokeConfig,
    *,
    environ: Mapping[str, str],
    tracing_configurator: Callable[[Settings], TracingConfigurationResult] = configure_tracing,
) -> dict[str, Any]:
    exporter = normalize_trace_exporter(config.trace_exporter)
    required_env_check = required_env_report(exporter, environ)
    evidence = observability_smoke_evidence(config=config, exporter=exporter)
    if required_env_check["status"] != "passed":
        return {
            "ok": False,
            "status": "skipped",
            "scope": "local_contract",
            "evidence": evidence,
            "checks": {"required_env": required_env_check},
            "error": "missing required observability environment",
        }

    settings = settings_from_config(config, environ)
    try:
        tracing_result = tracing_configurator(settings)
        redaction_report = run_redaction_check(environ)
        with trace_reactor_span(
            "reactor.release.observability_smoke",
            {
                "reactor.trace_exporter": exporter,
                "reactor.langsmith_project": config.langsmith_project,
            },
        ):
            span_report = {
                "status": "passed",
                "name": "reactor.release.observability_smoke",
            }
    except Exception as error:  # noqa: BLE001
        return {
            "ok": False,
            "status": "failed",
            "scope": "local_contract",
            "evidence": evidence,
            "checks": {
                "required_env": required_env_check,
                "tracing_config": {
                    "status": "failed",
                    "error": sanitize_error(str(error), environ),
                },
            },
        }

    checks = {
        "required_env": required_env_check,
        "tracing_config": tracing_config_report(tracing_result, settings),
        "redaction": redaction_report,
        "span": span_report,
    }
    ok = all(check.get("status") == "passed" for check in checks.values())
    return {
        "ok": ok,
        "status": "passed" if ok else "failed",
        "scope": "local_contract",
        "evidence": evidence,
        "checks": checks,
    }


def observability_smoke_evidence(
    *,
    config: ObservabilitySmokeConfig | None = None,
    exporter: str = "langsmith",
) -> dict[str, object]:
    config = config or ObservabilitySmokeConfig()
    return {
        "artifact": "reports/observability-smoke.json",
        "command": "uv run reactor-observability-smoke --output reports/observability-smoke.json",
        "owner": "reactor.observability",
        "mode": "langsmith_online_observability_contract",
        "observabilitySdk": observability_sdk_contract(),
        "observabilityTarget": {
            "traceProvider": exporter,
            "project": config.langsmith_project,
            "endpoint": config.langsmith_endpoint,
            "spanName": "reactor.release.observability_smoke",
            "secretFree": True,
        },
        "privacy": {
            "traceProvider": exporter,
            "hideInputs": True,
            "hideOutputs": True,
            "hideMetadata": True,
            "redactionCheck": "required",
            "redactionCoverage": list(REDACTION_COVERAGE_FIELDS),
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
    }


def observability_sdk_contract() -> dict[str, object]:
    return {
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
    }


def observability_smoke_diagnostics(
    *,
    config: ObservabilitySmokeConfig | None = None,
    environ: Mapping[str, str],
) -> dict[str, Any]:
    config = config or ObservabilitySmokeConfig()
    exporter = normalize_trace_exporter(config.trace_exporter)
    required_env_check = required_env_report(exporter, environ)
    ready = required_env_check["status"] == "passed"
    report: dict[str, Any] = {
        "ok": ready,
        "status": "ready" if ready else "skipped",
        "scope": "local_contract_diagnostics",
        "evidence": observability_smoke_evidence(config=config, exporter=exporter),
        "checks": {"required_env": required_env_check},
        "releaseGate": observability_smoke_release_gate(ready=ready),
    }
    if not ready:
        report["error"] = "missing required observability environment"
    return report


def observability_smoke_release_gate(*, ready: bool) -> dict[str, object]:
    if ready:
        return {
            "status": "ready",
            "blocksReleaseReadiness": False,
            "reason": None,
            "requiredReport": "observability_smoke",
            "remediation": [],
        }
    return {
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


def required_env_report(exporter: str, environ: Mapping[str, str]) -> dict[str, Any]:
    report: dict[str, Any] = {
        "status": "passed",
        "exporter": exporter,
    }
    if exporter != "langsmith":
        return report
    report["any_of"] = [list(LANGSMITH_KEY_ENV_NAMES)]
    if any(environ.get(name, "").strip() for name in LANGSMITH_KEY_ENV_NAMES):
        return report
    report["status"] = "failed"
    report["missing"] = ["LANGSMITH_API_KEY or REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"]
    return report


def settings_from_config(
    config: ObservabilitySmokeConfig,
    environ: Mapping[str, str],
) -> Settings:
    langsmith_api_key = (
        environ.get("REACTOR_OBSERVABILITY_LANGSMITH_API_KEY", "").strip()
        or environ.get("LANGSMITH_API_KEY", "").strip()
    )
    return Settings(
        observability_tracing_enabled=True,
        observability_trace_exporter=config.trace_exporter,
        observability_langsmith_project=(
            environ.get("REACTOR_OBSERVABILITY_LANGSMITH_PROJECT", "").strip()
            or config.langsmith_project
        ),
        observability_langsmith_endpoint=(
            environ.get("REACTOR_OBSERVABILITY_LANGSMITH_ENDPOINT", "").strip()
            or config.langsmith_endpoint
        ),
        observability_langsmith_api_key=langsmith_api_key,
        observability_langsmith_hide_inputs=True,
        observability_langsmith_hide_outputs=True,
        observability_langsmith_hide_metadata=True,
    )


def tracing_config_report(
    result: TracingConfigurationResult,
    settings: Settings,
) -> dict[str, object]:
    report: dict[str, object] = {
        "status": "passed" if result.enabled else "failed",
        "exporter": result.exporter,
        "project": settings.observability_langsmith_project,
        "hide_inputs": settings.observability_langsmith_hide_inputs,
        "hide_outputs": settings.observability_langsmith_hide_outputs,
        "hide_metadata": settings.observability_langsmith_hide_metadata,
    }
    if result.endpoint is not None:
        report["endpoint"] = result.endpoint
    return report


def run_redaction_check(environ: Mapping[str, str]) -> dict[str, object]:
    secret = next((value for value in environ.values() if len(value) >= 6), "secret-value")
    pii = "sample-user@example.com"
    attributes = clean_span_attributes(
        {
            "reactor.api_key": secret,
            "reactor.payload": {
                "password": secret,
                "query": f"api_key={secret}",
                "actor_email": pii,
            },
            "reactor.metadata": {
                "tenant_id": "tenant_1",
                "user_email": pii,
                "nested": [{"authorization": f"Bearer {secret}"}],
            },
        }
    )
    encoded = str(attributes)
    secret_redacted = attributes["reactor.api_key"] == REDACTED
    payload_redacted = secret not in encoded
    metadata_redacted = secret not in str(attributes["reactor.metadata"])
    pii_redacted = pii not in encoded
    return {
        "status": (
            "passed"
            if secret_redacted and payload_redacted and metadata_redacted and pii_redacted
            else "failed"
        ),
        "checkedFields": list(REDACTION_COVERAGE_FIELDS),
        "secret_redacted": secret_redacted,
        "payload_redacted": payload_redacted,
        "metadata_redacted": metadata_redacted,
        "pii_redacted": pii_redacted,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a local observability tracing and redaction smoke check."
    )
    parser.add_argument("--trace-exporter", default="langsmith", help="Trace exporter")
    parser.add_argument(
        "--langsmith-project",
        default="reactor-observability-smoke",
        help="LangSmith project used for the smoke configuration",
    )
    parser.add_argument(
        "--langsmith-endpoint",
        default="https://api.smith.langchain.com",
        help="LangSmith API endpoint",
    )
    parser.add_argument("--output", required=True, help="Path to write smoke report JSON")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = run_observability_smoke(
        ObservabilitySmokeConfig(
            trace_exporter=str(args.trace_exporter),
            langsmith_project=str(args.langsmith_project),
            langsmith_endpoint=str(args.langsmith_endpoint),
        ),
        environ=os.environ,
    )
    output_path = Path(str(args.output))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as output:
        write_report(report, output)
    return 0 if report["ok"] else 1
