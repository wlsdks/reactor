from __future__ import annotations

from typing import Any

from reactor.rag.text_splitters import LangChainTextSplitter, split_text


def test_langchain_text_splitter_uses_recursive_character_splitter(monkeypatch: Any) -> None:
    calls: list[dict[str, object]] = []

    class FakeRecursiveCharacterTextSplitter:
        def __init__(self, **kwargs: object) -> None:
            calls.append(dict(kwargs))

        def split_text(self, text: str) -> list[str]:
            return [text[:3], text[3:]]

    monkeypatch.setattr(
        "reactor.rag.text_splitters.LANGCHAIN_RECURSIVE_TEXT_SPLITTER",
        FakeRecursiveCharacterTextSplitter,
    )

    chunks = LangChainTextSplitter(max_chunk_chars=3, chunk_overlap=1).split("abcdef")

    assert chunks == ["abc", "def"]
    assert calls == [{"chunk_size": 3, "chunk_overlap": 1}]


def test_split_text_rejects_blank_content() -> None:
    try:
        split_text("  ")
    except ValueError as error:
        assert str(error) == "Document content is required"
    else:
        raise AssertionError("blank document content should fail")
