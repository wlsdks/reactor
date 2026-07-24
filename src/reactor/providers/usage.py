from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import ceil
from typing import cast


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int
    output_tokens: int
    max_output_tokens: int
    cached_tokens: int = 0
    reasoning_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def within_output_limit(self) -> bool:
        return self.output_tokens <= self.max_output_tokens


def estimate_token_count(text: str) -> int:
    normalized = text.strip()
    if not normalized:
        return 0
    return max(1, ceil(len(normalized) / 4))


def estimated_usage(input_text: str, output_text: str, *, max_output_tokens: int) -> TokenUsage:
    return TokenUsage(
        input_tokens=estimate_token_count(input_text),
        output_tokens=estimate_token_count(output_text),
        max_output_tokens=max_output_tokens,
    )


def usage_from_provider_metadata(
    message: object,
    *,
    max_output_tokens: int,
) -> TokenUsage | None:
    usage_metadata = _mapping_attribute(message, "usage_metadata")
    usage = _usage_from_langchain_usage_metadata(
        usage_metadata,
        max_output_tokens=max_output_tokens,
    )
    if usage is not None:
        return usage

    response_metadata = _mapping_attribute(message, "response_metadata")
    token_usage = _nested_mapping(response_metadata, "token_usage")
    return _usage_from_openai_token_usage(
        token_usage,
        max_output_tokens=max_output_tokens,
    )


def usage_from_langchain_usage_metadata(
    usage_metadata: Mapping[str, object],
    *,
    max_output_tokens: int,
) -> TokenUsage | None:
    return _usage_from_langchain_usage_metadata(
        usage_metadata,
        max_output_tokens=max_output_tokens,
    )


def _usage_from_langchain_usage_metadata(
    usage_metadata: Mapping[str, object],
    *,
    max_output_tokens: int,
) -> TokenUsage | None:
    input_tokens = _int_value(usage_metadata, "input_tokens")
    output_tokens = _int_value(usage_metadata, "output_tokens")
    if input_tokens is None or output_tokens is None:
        return None
    has_total_tokens, total_tokens = _optional_int_value(usage_metadata, "total_tokens")
    if has_total_tokens and (total_tokens is None or total_tokens != input_tokens + output_tokens):
        return None
    input_details = _nested_mapping(usage_metadata, "input_token_details")
    output_details = _nested_mapping(usage_metadata, "output_token_details")
    cached_tokens = _first_optional_int_value(input_details, ("cache_read", "cached_tokens"))
    reasoning_tokens = _first_optional_int_value(
        output_details,
        ("reasoning", "reasoning_tokens"),
    )
    if not _valid_detail_counts(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_tokens=cached_tokens,
        reasoning_tokens=reasoning_tokens,
    ):
        return None
    assert cached_tokens is not None
    assert reasoning_tokens is not None
    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        max_output_tokens=max_output_tokens,
        cached_tokens=cached_tokens,
        reasoning_tokens=reasoning_tokens,
    )


def _usage_from_openai_token_usage(
    token_usage: Mapping[str, object],
    *,
    max_output_tokens: int,
) -> TokenUsage | None:
    input_tokens = _int_value(token_usage, "prompt_tokens")
    output_tokens = _int_value(token_usage, "completion_tokens")
    if input_tokens is None or output_tokens is None:
        return None
    has_total_tokens, total_tokens = _optional_int_value(token_usage, "total_tokens")
    if has_total_tokens and (total_tokens is None or total_tokens != input_tokens + output_tokens):
        return None
    prompt_details = _nested_mapping(token_usage, "prompt_tokens_details")
    completion_details = _nested_mapping(token_usage, "completion_tokens_details")
    cached_tokens = _first_optional_int_value(prompt_details, ("cached_tokens", "cache_read"))
    reasoning_tokens = _first_optional_int_value(
        completion_details,
        ("reasoning_tokens", "reasoning"),
    )
    if not _valid_detail_counts(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_tokens=cached_tokens,
        reasoning_tokens=reasoning_tokens,
    ):
        return None
    assert cached_tokens is not None
    assert reasoning_tokens is not None
    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        max_output_tokens=max_output_tokens,
        cached_tokens=cached_tokens,
        reasoning_tokens=reasoning_tokens,
    )


def _mapping_attribute(source: object, name: str) -> Mapping[str, object]:
    if isinstance(source, Mapping):
        mapped_source = cast(Mapping[object, object], source)
        value = mapped_source.get(name)
        if isinstance(value, Mapping):
            return cast(Mapping[str, object], value)
        return {}
    value = getattr(source, name, None)
    if isinstance(value, Mapping):
        return cast(Mapping[str, object], value)
    return {}


def _nested_mapping(source: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = source.get(key)
    if isinstance(value, Mapping):
        return cast(Mapping[str, object], value)
    return {}


def _int_value(source: Mapping[str, object], key: str) -> int | None:
    value = source.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    return None


def _optional_int_value(source: Mapping[str, object], key: str) -> tuple[bool, int | None]:
    if key not in source:
        return False, None
    return True, _int_value(source, key)


def _first_optional_int_value(source: Mapping[str, object], keys: tuple[str, ...]) -> int | None:
    for key in keys:
        has_value, value = _optional_int_value(source, key)
        if not has_value:
            continue
        return value
    return 0


def _valid_detail_counts(
    *,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int | None,
    reasoning_tokens: int | None,
) -> bool:
    if cached_tokens is None or reasoning_tokens is None:
        return False
    return cached_tokens <= input_tokens and reasoning_tokens <= output_tokens
