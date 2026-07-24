from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from reactor.observability.tracing import TracingConfigurationResult
from reactor.release.backend_provider_smoke import (
    LiveBackendProviderSmokeConfig,
    main,
    run_live_backend_provider_smoke,
)


def test_live_backend_provider_smoke_configures_tracing_and_invokes_provider() -> None:
    factory = FakeFactory(
        response=FakeMessage(
            "pong",
            usage_metadata={
                "input_tokens": 8,
                "output_tokens": 2,
                "total_tokens": 10,
            },
        )
    )

    report = run_live_backend_provider_smoke(
        LiveBackendProviderSmokeConfig(provider="openai", model="gpt-5-mini"),
        factory=factory,
        environ={
            "OPENAI_API_KEY": "provider-key",
            "LANGSMITH_API_KEY": "langsmith-key",
        },
        tracing_configurator=fake_tracing_configurator,
    )

    assert report == {
        "ok": True,
        "status": "passed",
        "scope": "live",
        "provider": "openai",
        "model": "gpt-5-mini",
        "evidence": {
            "artifact": "reports/live-backend-provider-integration.json",
            "command": (
                "uv run reactor-live-backend-provider-smoke "
                "--output reports/live-backend-provider-integration.json"
            ),
            "owner": "reactor.release",
            "mode": "live_backend_provider_integration",
            "observabilityTarget": {
                "traceProvider": "langsmith",
                "project": "reactor-release-smoke",
                "endpoint": "https://api.smith.langchain.com",
                "spanName": "reactor.release.backend_provider_smoke",
                "secretFree": True,
            },
            "privacy": {
                "traceProvider": "langsmith",
                "hideInputs": True,
                "hideOutputs": True,
                "hideMetadata": True,
                "redactionCheck": "required",
            },
            "backendProviderIntegration": {
                "status": "verified",
                "invocationApi": "ainvoke",
                "provider": "openai",
                "model": "gpt-5-mini",
                "usageMetadata": {
                    "source": "LangChain AIMessage.usage_metadata",
                    "present": True,
                    "inputTokens": 8,
                    "outputTokens": 2,
                    "totalTokens": 10,
                    "totalMatchesBreakdown": True,
                },
                "requiredChecks": [
                    "required_env",
                    "tracing_config",
                    "chat_model_invoke",
                    "usage_metadata",
                ],
            },
        },
        "checks": {
            "required_env": {
                "status": "passed",
                "variables": ["OPENAI_API_KEY"],
                "tracing": {
                    "exporter": "langsmith",
                    "variables": ["LANGSMITH_API_KEY", "REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"],
                },
            },
            "tracing_config": {
                "status": "passed",
                "exporter": "langsmith",
                "endpoint": "https://api.smith.langchain.com",
                "hide_inputs": True,
                "hide_outputs": True,
                "hide_metadata": True,
            },
            "chat_model_invoke": {
                "status": "passed",
                "content_length": 4,
            },
            "usage_metadata": {
                "status": "passed",
                "source": "LangChain AIMessage.usage_metadata",
                "input_tokens": 8,
                "output_tokens": 2,
                "total_tokens": 10,
            },
        },
    }


def test_live_backend_provider_smoke_exercises_async_langchain_interface() -> None:
    message = FakeMessage(
        "pong",
        usage_metadata={
            "input_tokens": 8,
            "output_tokens": 2,
            "total_tokens": 10,
        },
    )

    class AsyncOnlyModel:
        async def ainvoke(self, prompt: str) -> FakeMessage:
            assert prompt == "Reply with pong."
            return message

        def invoke(self, _prompt: str) -> FakeMessage:
            raise AssertionError("sync invoke must not be used")

    class AsyncOnlyFactory:
        def create(self, *, provider: str, model: str) -> AsyncOnlyModel:
            assert provider == "openai"
            assert model == "gpt-5-mini"
            return AsyncOnlyModel()

    report = run_live_backend_provider_smoke(
        LiveBackendProviderSmokeConfig(provider="openai", model="gpt-5-mini"),
        factory=AsyncOnlyFactory(),
        environ={
            "OPENAI_API_KEY": "provider-key",
            "LANGSMITH_API_KEY": "langsmith-key",
        },
        tracing_configurator=fake_tracing_configurator,
    )

    assert report["ok"] is True
    assert report["checks"]["chat_model_invoke"]["status"] == "passed"


def test_live_backend_provider_smoke_skips_when_tracing_env_is_missing() -> None:
    report = run_live_backend_provider_smoke(
        LiveBackendProviderSmokeConfig(provider="openai", model="gpt-5-mini"),
        factory=FakeFactory(response=FakeMessage("pong")),
        environ={"OPENAI_API_KEY": "provider-key"},
        tracing_configurator=fake_tracing_configurator,
    )

    assert report["ok"] is False
    assert report["status"] == "skipped"
    assert report["checks"]["required_env"]["tracing_missing"] == [
        "LANGSMITH_API_KEY or REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"
    ]


def test_live_backend_provider_smoke_records_sanitized_provider_failure() -> None:
    report = run_live_backend_provider_smoke(
        LiveBackendProviderSmokeConfig(provider="openai", model="gpt-5-mini"),
        factory=FakeFactory(error=RuntimeError("bad provider-key langsmith-key")),
        environ={
            "OPENAI_API_KEY": "provider-key",
            "LANGSMITH_API_KEY": "langsmith-key",
        },
        tracing_configurator=fake_tracing_configurator,
    )

    assert report["ok"] is False
    assert report["status"] == "failed"
    assert report["checks"]["chat_model_invoke"] == {
        "status": "failed",
        "error": "bad [redacted] [redacted]",
    }


def test_live_backend_provider_smoke_rejects_malformed_langchain_usage_metadata() -> None:
    report = run_live_backend_provider_smoke(
        LiveBackendProviderSmokeConfig(provider="openai", model="gpt-5-mini"),
        factory=FakeFactory(
            response=FakeMessage(
                "pong",
                usage_metadata={
                    "input_tokens": 8,
                    "output_tokens": 2,
                    "total_tokens": 999,
                },
                response_metadata={
                    "token_usage": {
                        "prompt_tokens": 8,
                        "completion_tokens": 2,
                        "total_tokens": 10,
                    }
                },
            )
        ),
        environ={
            "OPENAI_API_KEY": "provider-key",
            "LANGSMITH_API_KEY": "langsmith-key",
        },
        tracing_configurator=fake_tracing_configurator,
    )

    assert report["ok"] is False
    assert report["status"] == "failed"
    assert report["checks"]["usage_metadata"] == {
        "status": "failed",
        "source": "LangChain AIMessage.usage_metadata",
        "reason": "malformed_usage_metadata",
        "error": "malformed provider usage metadata",
    }


def test_live_backend_provider_smoke_cli_writes_report(tmp_path: Path, monkeypatch: Any) -> None:
    output_path = tmp_path / "reports" / "release" / "backend-provider-smoke.json"

    monkeypatch.setenv("OPENAI_API_KEY", "provider-key")
    monkeypatch.setenv("LANGSMITH_API_KEY", "langsmith-key")
    monkeypatch.setattr(
        "reactor.release.backend_provider_smoke.LangChainChatModelFactory",
        lambda: FakeFactory(
            response=FakeMessage(
                "pong",
                usage_metadata={
                    "input_tokens": 8,
                    "output_tokens": 2,
                    "total_tokens": 10,
                },
            )
        ),
    )
    monkeypatch.setattr(
        "reactor.release.backend_provider_smoke.configure_tracing",
        fake_tracing_configurator,
    )

    exit_code = main(
        [
            "--provider",
            "openai",
            "--model",
            "gpt-5-mini",
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 0
    assert json.loads(output_path.read_text(encoding="utf-8"))["ok"] is True


def test_live_backend_provider_smoke_cli_defaults_to_settings_model(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    output_path = tmp_path / "backend-provider-smoke.json"

    monkeypatch.setenv("OPENAI_API_KEY", "provider-key")
    monkeypatch.setenv("LANGSMITH_API_KEY", "langsmith-key")
    monkeypatch.setenv("REACTOR_DEFAULT_MODEL_PROVIDER", "openai")
    monkeypatch.setenv("REACTOR_DEFAULT_MODEL", "gpt-5-mini")
    monkeypatch.setattr(
        "reactor.release.backend_provider_smoke.LangChainChatModelFactory",
        lambda: FakeFactory(
            response=FakeMessage(
                "pong",
                usage_metadata={
                    "input_tokens": 8,
                    "output_tokens": 2,
                    "total_tokens": 10,
                },
            )
        ),
    )
    monkeypatch.setattr(
        "reactor.release.backend_provider_smoke.configure_tracing",
        fake_tracing_configurator,
    )

    exit_code = main(["--output", str(output_path)])

    assert exit_code == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["provider"] == "openai"
    assert payload["model"] == "gpt-5-mini"


def fake_tracing_configurator(_: object) -> TracingConfigurationResult:
    return TracingConfigurationResult(
        enabled=True,
        exporter="langsmith",
        endpoint="https://api.smith.langchain.com",
    )


class FakeFactory:
    def __init__(
        self,
        *,
        response: FakeMessage | None = None,
        error: Exception | None = None,
    ) -> None:
        self._response = response
        self._error = error

    def create(self, *, provider: str, model: str) -> FakeModel:
        _ = provider, model
        return FakeModel(response=self._response, error=self._error)


class FakeModel:
    def __init__(
        self,
        *,
        response: FakeMessage | None,
        error: Exception | None,
    ) -> None:
        self._response = response
        self._error = error

    async def ainvoke(self, prompt: str) -> FakeMessage:
        _ = prompt
        if self._error is not None:
            raise self._error
        if self._response is None:
            raise RuntimeError("missing fake response")
        return self._response

    def invoke(self, _prompt: str) -> FakeMessage:
        raise AssertionError("sync invoke must not be used")


class FakeMessage:
    def __init__(
        self,
        content: str,
        usage_metadata: dict[str, object] | None = None,
        response_metadata: dict[str, object] | None = None,
    ) -> None:
        self.content = content
        self.usage_metadata = usage_metadata or {}
        self.response_metadata = response_metadata or {}
