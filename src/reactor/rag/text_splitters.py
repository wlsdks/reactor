from __future__ import annotations

from importlib import import_module
from typing import Any, Protocol, cast

LANGCHAIN_TEXT_SPLITTERS_MODULE = cast(Any, import_module("langchain_text_splitters"))
LANGCHAIN_RECURSIVE_TEXT_SPLITTER: Any = (
    LANGCHAIN_TEXT_SPLITTERS_MODULE.RecursiveCharacterTextSplitter
)


class TextSplitter(Protocol):
    def split(self, content: str) -> list[str]: ...


class LangChainTextSplitter:
    def __init__(self, *, max_chunk_chars: int = 4_000, chunk_overlap: int = 200) -> None:
        self._max_chunk_chars = max_chunk_chars
        self._chunk_overlap = chunk_overlap

    def split(self, content: str) -> list[str]:
        return split_text(
            content,
            max_chunk_chars=self._max_chunk_chars,
            chunk_overlap=self._chunk_overlap,
        )


def split_text(
    content: str,
    *,
    max_chunk_chars: int = 4_000,
    chunk_overlap: int = 200,
) -> list[str]:
    stripped = content.strip()
    if not stripped:
        raise ValueError("Document content is required")
    splitter = LANGCHAIN_RECURSIVE_TEXT_SPLITTER(
        chunk_size=max_chunk_chars,
        chunk_overlap=chunk_overlap,
    )
    return [chunk for chunk in splitter.split_text(stripped) if chunk.strip()]
