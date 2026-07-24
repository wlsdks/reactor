from __future__ import annotations

import argparse
import asyncio
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from reactor.core.settings import Settings
from reactor.providers.chat_models import ChatModelFactory, LangChainChatModelFactory
from reactor.release.readiness import write_report

PROVIDER_REQUIRED_ENV: dict[str, tuple[str, ...]] = {
    "anthropic": ("ANTHROPIC_API_KEY",),
    "google": ("GOOGLE_API_KEY",),
    "openai": ("OPENAI_API_KEY",),
}


@dataclass(frozen=True)
class LiveProviderSmokeConfig:
    provider: str
    model: str
    prompt: str = "Reply with pong."


def run_live_provider_smoke(
    config: LiveProviderSmokeConfig,
    *,
    factory: ChatModelFactory,
    environ: Mapping[str, str],
) -> dict[str, Any]:
    required_env = required_env_for_provider(config.provider)
    missing_env = [name for name in required_env if not environ.get(name, "").strip()]
    base_report = {
        "scope": "live",
        "provider": config.provider,
        "model": config.model,
    }
    if missing_env:
        return {
            **base_report,
            "ok": False,
            "status": "skipped",
            "checks": {
                "required_env": {
                    "status": "failed",
                    "variables": list(required_env),
                    "missing": missing_env,
                }
            },
            "error": "missing required provider environment",
        }
    try:
        model = factory.create(provider=config.provider, model=config.model)
        response = asyncio.run(model.ainvoke(config.prompt))
        content = response_content(response)
    except Exception as error:  # noqa: BLE001
        return {
            **base_report,
            "ok": False,
            "status": "failed",
            "checks": {
                "required_env": {
                    "status": "passed",
                    "variables": list(required_env),
                },
                "chat_model_invoke": {
                    "status": "failed",
                    "error": sanitize_error(str(error), environ),
                },
            },
        }
    return {
        **base_report,
        "ok": True,
        "status": "passed",
        "evidence": provider_runtime_smoke_evidence(config),
        "checks": {
            "required_env": {
                "status": "passed",
                "variables": list(required_env),
            },
            "chat_model_invoke": {
                "status": "passed",
                "content_length": len(content),
            },
        },
    }


def provider_runtime_smoke_evidence(config: LiveProviderSmokeConfig) -> dict[str, object]:
    return {
        "artifact": "reports/live-provider-runtime-smoke.json",
        "command": (
            "uv run reactor-live-provider-smoke --output reports/live-provider-runtime-smoke.json"
        ),
        "owner": "reactor.release",
        "mode": "live_provider_runtime_smoke",
        "providerRuntimeSmoke": {
            "status": "verified",
            "invocationApi": "ainvoke",
            "framework": "langchain",
            "interface": "ChatModelFactory",
            "provider": config.provider,
            "model": config.model,
            "requiredChecks": [
                "required_env",
                "chat_model_invoke",
            ],
        },
    }


def required_env_for_provider(provider: str) -> tuple[str, ...]:
    return PROVIDER_REQUIRED_ENV.get(provider, ())


def response_content(response: Any) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(str(item) for item in cast(list[object], content))
    return str(content)


def sanitize_error(message: str, environ: Mapping[str, str]) -> str:
    sanitized = message
    for value in environ.values():
        if value and len(value) >= 6:
            sanitized = sanitized.replace(value, "[redacted]")
    return sanitized


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a live LangChain provider smoke check.")
    parser.add_argument("--provider", default=None, help="LangChain provider name")
    parser.add_argument("--model", default=None, help="Provider model name")
    parser.add_argument("--prompt", default="Reply with pong.", help="Smoke prompt")
    parser.add_argument("--output", required=True, help="Path to write smoke report JSON")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    settings = Settings()
    report = run_live_provider_smoke(
        LiveProviderSmokeConfig(
            provider=str(args.provider or settings.default_model_provider),
            model=str(args.model or settings.default_model),
            prompt=str(args.prompt),
        ),
        factory=LangChainChatModelFactory(),
        environ=os.environ,
    )
    output_path = Path(str(args.output))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as output:
        write_report(report, output)
    return 0 if report["ok"] else 1
