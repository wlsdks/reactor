from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from reactor.release.provider_smoke import (
    LiveProviderSmokeConfig,
    main,
    run_live_provider_smoke,
)


def test_live_provider_smoke_invokes_langchain_chat_model() -> None:
    factory = FakeFactory(response=FakeMessage("pong"))

    report = run_live_provider_smoke(
        LiveProviderSmokeConfig(provider="openai", model="gpt-5-mini"),
        factory=factory,
        environ={"OPENAI_API_KEY": "test-key"},
    )

    assert report == {
        "ok": True,
        "status": "passed",
        "scope": "live",
        "provider": "openai",
        "model": "gpt-5-mini",
        "evidence": {
            "artifact": "reports/live-provider-runtime-smoke.json",
            "command": (
                "uv run reactor-live-provider-smoke "
                "--output reports/live-provider-runtime-smoke.json"
            ),
            "owner": "reactor.release",
            "mode": "live_provider_runtime_smoke",
            "providerRuntimeSmoke": {
                "status": "verified",
                "invocationApi": "ainvoke",
                "framework": "langchain",
                "interface": "ChatModelFactory",
                "provider": "openai",
                "model": "gpt-5-mini",
                "requiredChecks": [
                    "required_env",
                    "chat_model_invoke",
                ],
            },
        },
        "checks": {
            "required_env": {"status": "passed", "variables": ["OPENAI_API_KEY"]},
            "chat_model_invoke": {
                "status": "passed",
                "content_length": 4,
            },
        },
    }
    assert factory.calls == [{"provider": "openai", "model": "gpt-5-mini"}]


def test_live_provider_smoke_exercises_async_langchain_interface() -> None:
    message = FakeMessage("pong")

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

    report = run_live_provider_smoke(
        LiveProviderSmokeConfig(provider="openai", model="gpt-5-mini"),
        factory=AsyncOnlyFactory(),
        environ={"OPENAI_API_KEY": "test-key"},
    )

    assert report["ok"] is True
    assert report["checks"]["chat_model_invoke"]["status"] == "passed"


def test_live_provider_smoke_skips_when_required_env_is_missing() -> None:
    report = run_live_provider_smoke(
        LiveProviderSmokeConfig(provider="anthropic", model="claude-sonnet-5"),
        factory=FakeFactory(response=FakeMessage("pong")),
        environ={},
    )

    assert report == {
        "ok": False,
        "status": "skipped",
        "scope": "live",
        "provider": "anthropic",
        "model": "claude-sonnet-5",
        "checks": {
            "required_env": {
                "status": "failed",
                "variables": ["ANTHROPIC_API_KEY"],
                "missing": ["ANTHROPIC_API_KEY"],
            }
        },
        "error": "missing required provider environment",
    }


def test_live_provider_smoke_allows_local_ollama_without_provider_key() -> None:
    factory = FakeFactory(response=FakeMessage("pong"))

    report = run_live_provider_smoke(
        LiveProviderSmokeConfig(provider="ollama", model="gemma4:12b"),
        factory=factory,
        environ={},
    )

    assert report["ok"] is True
    assert report["status"] == "passed"
    assert report["provider"] == "ollama"
    assert report["model"] == "gemma4:12b"
    assert report["checks"]["required_env"] == {"status": "passed", "variables": []}
    assert factory.calls == [{"provider": "ollama", "model": "gemma4:12b"}]


def test_live_provider_smoke_records_sanitized_model_failure() -> None:
    report = run_live_provider_smoke(
        LiveProviderSmokeConfig(provider="openai", model="gpt-5-mini"),
        factory=FakeFactory(error=RuntimeError("bad key sk-live-secret")),
        environ={"OPENAI_API_KEY": "sk-live-secret"},
    )

    assert report["ok"] is False
    assert report["status"] == "failed"
    assert report["checks"]["chat_model_invoke"] == {
        "status": "failed",
        "error": "bad key [redacted]",
    }


def test_live_provider_smoke_cli_writes_report(tmp_path: Path, monkeypatch: Any) -> None:
    output_path = tmp_path / "reports" / "release" / "provider-smoke.json"

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "reactor.release.provider_smoke.LangChainChatModelFactory",
        lambda: FakeFactory(response=FakeMessage("pong")),
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


def test_live_provider_smoke_cli_defaults_to_settings_model(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    output_path = tmp_path / "provider-smoke.json"

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("REACTOR_DEFAULT_MODEL_PROVIDER", "openai")
    monkeypatch.setenv("REACTOR_DEFAULT_MODEL", "gpt-5-mini")
    monkeypatch.setattr(
        "reactor.release.provider_smoke.LangChainChatModelFactory",
        lambda: FakeFactory(response=FakeMessage("pong")),
    )

    exit_code = main(["--output", str(output_path)])

    assert exit_code == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["provider"] == "openai"
    assert payload["model"] == "gpt-5-mini"


class FakeFactory:
    def __init__(
        self,
        *,
        response: FakeMessage | None = None,
        error: Exception | None = None,
    ) -> None:
        self._response = response
        self._error = error
        self.calls: list[dict[str, str]] = []

    def create(self, *, provider: str, model: str) -> FakeModel:
        self.calls.append({"provider": provider, "model": model})
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
    def __init__(self, content: str) -> None:
        self.content = content
