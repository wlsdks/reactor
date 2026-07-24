from __future__ import annotations

from typing import Any

from reactor.providers.chat_models import LangChainChatModelFactory, model_identifier


def test_model_identifier_uses_langchain_standard_provider_model_format() -> None:
    assert model_identifier(provider="openai", model="gpt-5-mini") == "openai:gpt-5-mini"
    assert model_identifier(provider="anthropic", model="claude-sonnet-5") == (
        "anthropic:claude-sonnet-5"
    )
    assert model_identifier(provider="", model="local-model") == "local-model"


def test_langchain_chat_model_factory_delegates_to_init_chat_model(monkeypatch: Any) -> None:
    calls: list[dict[str, object]] = []
    expected_model = object()

    def fake_init_chat_model(model: str, **kwargs: object) -> object:
        calls.append({"model": model, **kwargs})
        return expected_model

    monkeypatch.setattr(
        "reactor.providers.chat_models.LANGCHAIN_INIT_CHAT_MODEL",
        fake_init_chat_model,
    )

    result = LangChainChatModelFactory().create(provider="openai", model="gpt-5-mini")

    assert result is expected_model
    assert calls == [{"model": "openai:gpt-5-mini", "max_retries": 0}]
