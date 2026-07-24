from __future__ import annotations

from importlib import import_module
from typing import Any, Protocol, cast

LANGCHAIN_CHAT_MODELS_MODULE = cast(Any, import_module("langchain.chat_models"))
LANGCHAIN_INIT_CHAT_MODEL: Any = LANGCHAIN_CHAT_MODELS_MODULE.init_chat_model
PROVIDER_INTERNAL_MAX_RETRIES = 0


class ChatModelFactory(Protocol):
    def create(self, *, provider: str, model: str) -> Any: ...


class LangChainChatModelFactory:
    def create(self, *, provider: str, model: str) -> Any:
        return LANGCHAIN_INIT_CHAT_MODEL(
            model_identifier(provider=provider, model=model),
            max_retries=PROVIDER_INTERNAL_MAX_RETRIES,
        )


def model_identifier(*, provider: str, model: str) -> str:
    return f"{provider}:{model}" if provider.strip() else model
