from __future__ import annotations

from importlib import import_module
from typing import Any, Protocol, cast

from reactor.core.settings import Settings

LANGCHAIN_EMBEDDINGS_MODULE = cast(Any, import_module("langchain.embeddings"))
LANGCHAIN_INIT_EMBEDDINGS: Any = LANGCHAIN_EMBEDDINGS_MODULE.init_embeddings


class EmbeddingProvider(Protocol):
    async def embed_query(self, text: str) -> list[float]: ...


class LangChainEmbeddingProvider:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._embeddings: Any | None = None

    async def embed_query(self, text: str) -> list[float]:
        embeddings = self.langchain_embeddings()
        result = await embeddings.aembed_query(text)
        return [float(value) for value in result]

    def langchain_embeddings(self) -> Any:
        if self._embeddings is None:
            self._embeddings = LANGCHAIN_INIT_EMBEDDINGS(
                self._settings.default_embedding_model,
                provider=self._settings.default_embedding_provider,
            )
        return self._embeddings
