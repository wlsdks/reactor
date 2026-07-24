from __future__ import annotations

from collections.abc import Sequence
from importlib import import_module
from typing import Any, cast

from langchain_core.messages import AnyMessage

LANGCHAIN_MESSAGES_MODULE = cast(Any, import_module("langchain_core.messages"))
LANGCHAIN_TRIM_MESSAGES: Any = LANGCHAIN_MESSAGES_MODULE.trim_messages


def trim_to_message_pair_boundary(
    messages: Sequence[AnyMessage],
    *,
    max_messages: int,
) -> list[AnyMessage]:
    if max_messages <= 0:
        return []
    all_messages = list(messages)
    trimmed = cast(
        list[AnyMessage],
        LANGCHAIN_TRIM_MESSAGES(
            all_messages,
            max_tokens=max_messages,
            token_counter=len,
            strategy="last",
        ),
    )
    if not trimmed:
        return []
    if trimmed[0].type == "tool":
        start_index = len(all_messages) - len(trimmed)
        if start_index > 0 and all_messages[start_index - 1].type == "ai":
            return [all_messages[start_index - 1], *trimmed]
        return trimmed
    if len(trimmed) > 1 and trimmed[0].type == "ai" and trimmed[1].type == "tool":
        return trimmed
    return trimmed
