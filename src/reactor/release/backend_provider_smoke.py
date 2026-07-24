from __future__ import annotations

import argparse
import asyncio
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from reactor.core.settings import Settings
from reactor.observability.tracing import (
    TracingConfigurationResult,
    configure_tracing,
    trace_reactor_span,
)
from reactor.providers.chat_models import ChatModelFactory, LangChainChatModelFactory
from reactor.providers.usage import TokenUsage, usage_from_langchain_usage_metadata
from reactor.release.provider_smoke import (
    required_env_for_provider,
    response_content,
    sanitize_error,
)
from reactor.release.readiness import write_report

LANGSMITH_KEY_ENV_NAMES = (
    "LANGSMITH_API_KEY",
    "REACTOR_OBSERVABILITY_LANGSMITH_API_KEY",
)


@dataclass(frozen=True)
class LiveBackendProviderSmokeConfig:
    provider: str
    model: str
    trace_exporter: str = "langsmith"
    langsmith_project: str = "reactor-release-smoke"
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    prompt: str = "Reply with pong."


def run_live_backend_provider_smoke(
    config: LiveBackendProviderSmokeConfig,
    *,
    factory: ChatModelFactory,
    environ: Mapping[str, str],
    tracing_configurator: Callable[[Settings], TracingConfigurationResult] = configure_tracing,
) -> dict[str, Any]:
    provider_required_env = required_env_for_provider(config.provider)
    missing_provider_env = [
        name for name in provider_required_env if not environ.get(name, "").strip()
    ]
    tracing_missing = missing_tracing_env(config, environ)
    base_report: dict[str, Any] = {
        "scope": "live",
        "provider": config.provider,
        "model": config.model,
    }
    required_env_check: dict[str, Any] = {
        "status": "failed" if missing_provider_env or tracing_missing else "passed",
        "variables": list(provider_required_env),
        "tracing": tracing_requirement(config),
    }
    if missing_provider_env:
        required_env_check["missing"] = missing_provider_env
    if tracing_missing:
        required_env_check["tracing_missing"] = tracing_missing
    if missing_provider_env or tracing_missing:
        return {
            **base_report,
            "ok": False,
            "status": "skipped",
            "checks": {
                "required_env": required_env_check,
            },
            "error": "missing required backend/provider environment",
        }

    settings = settings_from_config(config, environ)
    try:
        tracing_result = tracing_configurator(settings)
    except Exception as error:  # noqa: BLE001
        return {
            **base_report,
            "ok": False,
            "status": "failed",
            "checks": {
                "required_env": required_env_check,
                "tracing_config": {
                    "status": "failed",
                    "error": sanitize_error(str(error), environ),
                },
            },
        }

    try:
        with trace_reactor_span(
            "reactor.release.backend_provider_smoke",
            {
                "reactor.provider": config.provider,
                "reactor.model": config.model,
                "reactor.trace_exporter": tracing_result.exporter,
            },
        ):
            model = factory.create(provider=config.provider, model=config.model)
            response = asyncio.run(model.ainvoke(config.prompt))
            content = response_content(response)
            usage_metadata = langchain_usage_metadata(response)
            usage = usage_from_langchain_usage_metadata(
                usage_metadata,
                max_output_tokens=settings.max_output_tokens,
            )
    except Exception as error:  # noqa: BLE001
        return {
            **base_report,
            "ok": False,
            "status": "failed",
            "checks": {
                "required_env": required_env_check,
                "tracing_config": tracing_config_report(tracing_result, settings),
                "chat_model_invoke": {
                    "status": "failed",
                    "error": sanitize_error(str(error), environ),
                },
            },
        }
    if usage is None:
        return {
            **base_report,
            "ok": False,
            "status": "failed",
            "checks": {
                "required_env": required_env_check,
                "tracing_config": tracing_config_report(tracing_result, settings),
                "chat_model_invoke": {
                    "status": "passed",
                    "content_length": len(content),
                },
                "usage_metadata": {
                    "status": "failed",
                    "source": "LangChain AIMessage.usage_metadata",
                    "reason": usage_metadata_failure_reason(usage_metadata),
                    "error": usage_metadata_failure_error(usage_metadata),
                },
            },
        }

    return {
        **base_report,
        "ok": True,
        "status": "passed",
        "evidence": backend_provider_integration_evidence(
            config,
            tracing_result,
            settings,
            usage,
        ),
        "checks": {
            "required_env": required_env_check,
            "tracing_config": tracing_config_report(tracing_result, settings),
            "chat_model_invoke": {
                "status": "passed",
                "content_length": len(content),
            },
            "usage_metadata": usage_metadata_check(usage),
        },
    }


def backend_provider_integration_evidence(
    config: LiveBackendProviderSmokeConfig,
    result: TracingConfigurationResult,
    settings: Settings,
    usage: TokenUsage,
) -> dict[str, object]:
    return {
        "artifact": "reports/live-backend-provider-integration.json",
        "command": (
            "uv run reactor-live-backend-provider-smoke "
            "--output reports/live-backend-provider-integration.json"
        ),
        "owner": "reactor.release",
        "mode": "live_backend_provider_integration",
        "observabilityTarget": {
            "traceProvider": result.exporter,
            "project": settings.observability_langsmith_project,
            "endpoint": result.endpoint or settings.observability_langsmith_endpoint,
            "spanName": "reactor.release.backend_provider_smoke",
            "secretFree": True,
        },
        "privacy": {
            "traceProvider": result.exporter,
            "hideInputs": settings.observability_langsmith_hide_inputs,
            "hideOutputs": settings.observability_langsmith_hide_outputs,
            "hideMetadata": settings.observability_langsmith_hide_metadata,
            "redactionCheck": "required",
        },
        "backendProviderIntegration": {
            "status": "verified",
            "invocationApi": "ainvoke",
            "provider": config.provider,
            "model": config.model,
            "usageMetadata": usage_metadata_evidence(usage),
            "requiredChecks": [
                "required_env",
                "tracing_config",
                "chat_model_invoke",
                "usage_metadata",
            ],
        },
    }


def langchain_usage_metadata(message: object) -> Mapping[str, object]:
    if isinstance(message, Mapping):
        mapped_message = cast(Mapping[object, object], message)
        value = mapped_message.get("usage_metadata")
        if isinstance(value, Mapping):
            return cast(Mapping[str, object], value)
        return {}
    value = getattr(message, "usage_metadata", None)
    if isinstance(value, Mapping):
        return cast(Mapping[str, object], value)
    return {}


def usage_metadata_failure_reason(usage_metadata: Mapping[str, object]) -> str:
    return "malformed_usage_metadata" if usage_metadata else "missing_usage_metadata"


def usage_metadata_failure_error(usage_metadata: Mapping[str, object]) -> str:
    if usage_metadata:
        return "malformed provider usage metadata"
    return "missing provider usage metadata"


def usage_metadata_evidence(usage: TokenUsage) -> dict[str, object]:
    return {
        "source": "LangChain AIMessage.usage_metadata",
        "present": True,
        "inputTokens": usage.input_tokens,
        "outputTokens": usage.output_tokens,
        "totalTokens": usage.total_tokens,
        "totalMatchesBreakdown": True,
    }


def usage_metadata_check(usage: TokenUsage) -> dict[str, object]:
    return {
        "status": "passed",
        "source": "LangChain AIMessage.usage_metadata",
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "total_tokens": usage.total_tokens,
    }


def missing_tracing_env(
    config: LiveBackendProviderSmokeConfig,
    environ: Mapping[str, str],
) -> list[str]:
    if config.trace_exporter.strip().lower().replace("-", "_") != "langsmith":
        return []
    if any(environ.get(name, "").strip() for name in LANGSMITH_KEY_ENV_NAMES):
        return []
    return ["LANGSMITH_API_KEY or REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"]


def tracing_requirement(config: LiveBackendProviderSmokeConfig) -> dict[str, object]:
    if config.trace_exporter.strip().lower().replace("-", "_") == "langsmith":
        return {
            "exporter": "langsmith",
            "variables": list(LANGSMITH_KEY_ENV_NAMES),
        }
    return {
        "exporter": config.trace_exporter,
        "variables": [],
    }


def settings_from_config(
    config: LiveBackendProviderSmokeConfig,
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
    )


def tracing_config_report(
    result: TracingConfigurationResult,
    settings: Settings,
) -> dict[str, object]:
    report: dict[str, object] = {
        "status": "passed" if result.enabled else "failed",
        "exporter": result.exporter,
        "hide_inputs": settings.observability_langsmith_hide_inputs,
        "hide_outputs": settings.observability_langsmith_hide_outputs,
        "hide_metadata": settings.observability_langsmith_hide_metadata,
    }
    if result.endpoint is not None:
        report["endpoint"] = result.endpoint
    return report


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a live backend/provider tracing integration smoke check."
    )
    parser.add_argument("--provider", default=None, help="LangChain provider name")
    parser.add_argument("--model", default=None, help="Provider model name")
    parser.add_argument("--prompt", default="Reply with pong.", help="Smoke prompt")
    parser.add_argument("--trace-exporter", default="langsmith", help="Trace exporter")
    parser.add_argument("--output", required=True, help="Path to write smoke report JSON")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    settings = Settings()
    report = run_live_backend_provider_smoke(
        LiveBackendProviderSmokeConfig(
            provider=str(args.provider or settings.default_model_provider),
            model=str(args.model or settings.default_model),
            prompt=str(args.prompt),
            trace_exporter=str(args.trace_exporter),
        ),
        factory=LangChainChatModelFactory(),
        environ=os.environ,
    )
    output_path = Path(str(args.output))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as output:
        write_report(report, output)
    return 0 if report["ok"] else 1
