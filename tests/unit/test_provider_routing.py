from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage

from reactor.agents.runner import run_once
from reactor.core.settings import Settings
from reactor.providers.routing import ModelProfile, ProviderFallback, ProviderRouter
from reactor.providers.usage import TokenUsage, estimated_usage, usage_from_provider_metadata


def test_provider_router_selects_first_enabled_profile() -> None:
    router = ProviderRouter(
        profiles=[
            ModelProfile(name="fast", provider="openai", model="gpt-5-mini", enabled=False),
            ModelProfile(name="primary", provider="anthropic", model="claude-sonnet-5"),
        ]
    )

    selected = router.select_profile("primary")

    assert selected.provider == "anthropic"
    assert selected.model == "claude-sonnet-5"


def test_provider_router_selects_fallback_profile_with_runtime_metadata() -> None:
    router = ProviderRouter(
        profiles=[
            ModelProfile(name="primary", provider="openai", model="gpt-5"),
            ModelProfile(name="fallback", provider="anthropic", model="claude-sonnet-5"),
        ]
    )

    selected, fallback = router.select_fallback_profile(
        failed_provider="openai",
        failed_model="gpt-5",
        reason="rate_limited",
        latency_ms=250,
        cost_usd=0.004,
    )

    assert selected.name == "fallback"
    assert fallback.as_metadata() == {
        "from_provider": "openai",
        "from_model": "gpt-5",
        "to_provider": "anthropic",
        "to_model": "claude-sonnet-5",
        "reason": "rate_limited",
        "latency_ms": 250,
        "cost_usd": 0.004,
    }


def test_provider_router_rejects_fallback_when_no_alternate_enabled_profile_exists() -> None:
    router = ProviderRouter(
        profiles=[
            ModelProfile(name="primary", provider="openai", model="gpt-5"),
            ModelProfile(
                name="disabled-fallback",
                provider="anthropic",
                model="claude-sonnet-5",
                enabled=False,
            ),
        ]
    )

    with pytest.raises(ValueError, match="no fallback model profile is available"):
        router.select_fallback_profile(
            failed_provider="openai",
            failed_model="gpt-5",
            reason="rate_limited",
            latency_ms=250,
            cost_usd=0.004,
        )


@pytest.mark.parametrize(
    ("latency_ms", "cost_usd", "message"),
    [
        (-1, 0.004, "latency_ms must be non-negative"),
        (250, -0.001, "cost_usd must be non-negative"),
    ],
)
def test_provider_router_rejects_negative_fallback_measurements(
    latency_ms: int,
    cost_usd: float,
    message: str,
) -> None:
    router = ProviderRouter(
        profiles=[
            ModelProfile(name="primary", provider="openai", model="gpt-5"),
            ModelProfile(name="fallback", provider="anthropic", model="claude-sonnet-5"),
        ]
    )

    with pytest.raises(ValueError, match=message):
        router.select_fallback_profile(
            failed_provider="openai",
            failed_model="gpt-5",
            reason="rate_limited",
            latency_ms=latency_ms,
            cost_usd=cost_usd,
        )


def test_provider_fallback_records_runtime_metadata() -> None:
    fallback = ProviderFallback(
        from_provider="openai",
        from_model="gpt-5",
        to_provider="anthropic",
        to_model="claude-sonnet-5",
        reason="rate_limited",
        latency_ms=123,
        cost_usd=0.002,
    )

    assert fallback.as_metadata() == {
        "from_provider": "openai",
        "from_model": "gpt-5",
        "to_provider": "anthropic",
        "to_model": "claude-sonnet-5",
        "reason": "rate_limited",
        "latency_ms": 123,
        "cost_usd": 0.002,
    }


def test_token_usage_tracks_total_and_limit_status() -> None:
    usage = TokenUsage(input_tokens=100, output_tokens=20, max_output_tokens=25)

    assert usage.total_tokens == 120
    assert usage.within_output_limit is True


def test_estimated_usage_produces_deterministic_nonzero_counts() -> None:
    usage = estimated_usage("hello", "world response", max_output_tokens=10)

    assert usage.input_tokens == 2
    assert usage.output_tokens == 4
    assert usage.total_tokens == 6
    assert usage.within_output_limit is True


def test_usage_from_langchain_usage_metadata_prefers_provider_counts() -> None:
    message = AIMessage(
        content="answer",
        usage_metadata={
            "input_tokens": 120,
            "output_tokens": 35,
            "total_tokens": 155,
            "input_token_details": {"cache_read": 42},
            "output_token_details": {"reasoning": 7},
        },
    )

    usage = usage_from_provider_metadata(message, max_output_tokens=100)

    assert usage == TokenUsage(
        input_tokens=120,
        output_tokens=35,
        max_output_tokens=100,
        cached_tokens=42,
        reasoning_tokens=7,
    )


def test_usage_from_langchain_usage_metadata_rejects_mismatched_total_tokens() -> None:
    message = AIMessage(
        content="answer",
        usage_metadata={
            "input_tokens": 120,
            "output_tokens": 35,
            "total_tokens": 999,
        },
    )

    usage = usage_from_provider_metadata(message, max_output_tokens=100)

    assert usage is None


def test_usage_from_langchain_usage_metadata_rejects_negative_total_tokens() -> None:
    message = AIMessage(
        content="answer",
        usage_metadata={
            "input_tokens": 120,
            "output_tokens": 35,
            "total_tokens": -1,
        },
    )

    usage = usage_from_provider_metadata(message, max_output_tokens=100)

    assert usage is None


def test_usage_from_langchain_usage_metadata_rejects_negative_counts() -> None:
    message = AIMessage(
        content="answer",
        usage_metadata={
            "input_tokens": -1,
            "output_tokens": 35,
            "total_tokens": 34,
        },
    )

    usage = usage_from_provider_metadata(message, max_output_tokens=100)

    assert usage is None


def test_usage_from_langchain_usage_metadata_rejects_negative_detail_counts() -> None:
    message = AIMessage(
        content="answer",
        usage_metadata={
            "input_tokens": 120,
            "output_tokens": 35,
            "total_tokens": 155,
            "input_token_details": {"cache_read": -1},
        },
    )

    usage = usage_from_provider_metadata(message, max_output_tokens=100)

    assert usage is None


def test_usage_from_langchain_usage_metadata_rejects_detail_counts_above_parent_counts() -> None:
    message = AIMessage(
        content="answer",
        usage_metadata={
            "input_tokens": 120,
            "output_tokens": 35,
            "total_tokens": 155,
            "input_token_details": {"cache_read": 121},
        },
    )

    usage = usage_from_provider_metadata(message, max_output_tokens=100)

    assert usage is None


def test_usage_from_serialized_langchain_usage_metadata_prefers_provider_counts() -> None:
    message = {
        "content": "answer",
        "usage_metadata": {
            "input_tokens": 91,
            "output_tokens": 13,
            "total_tokens": 104,
            "input_token_details": {"cached_tokens": 8},
            "output_token_details": {"reasoning_tokens": 3},
        },
    }

    usage = usage_from_provider_metadata(message, max_output_tokens=100)

    assert usage == TokenUsage(
        input_tokens=91,
        output_tokens=13,
        max_output_tokens=100,
        cached_tokens=8,
        reasoning_tokens=3,
    )


def test_usage_from_openai_response_metadata_supports_legacy_token_usage_shape() -> None:
    message = AIMessage(
        content="answer",
        response_metadata={
            "token_usage": {
                "prompt_tokens": 80,
                "completion_tokens": 20,
                "prompt_tokens_details": {"cached_tokens": 11},
                "completion_tokens_details": {"reasoning_tokens": 5},
            }
        },
    )

    usage = usage_from_provider_metadata(message, max_output_tokens=100)

    assert usage == TokenUsage(
        input_tokens=80,
        output_tokens=20,
        max_output_tokens=100,
        cached_tokens=11,
        reasoning_tokens=5,
    )


def test_usage_from_openai_response_metadata_rejects_mismatched_total_tokens() -> None:
    message = AIMessage(
        content="answer",
        response_metadata={
            "token_usage": {
                "prompt_tokens": 80,
                "completion_tokens": 20,
                "total_tokens": 999,
            }
        },
    )

    usage = usage_from_provider_metadata(message, max_output_tokens=100)

    assert usage is None


def test_usage_from_openai_response_metadata_rejects_negative_total_tokens() -> None:
    message = AIMessage(
        content="answer",
        response_metadata={
            "token_usage": {
                "prompt_tokens": 80,
                "completion_tokens": 20,
                "total_tokens": -1,
            }
        },
    )

    usage = usage_from_provider_metadata(message, max_output_tokens=100)

    assert usage is None


def test_usage_from_openai_response_metadata_rejects_negative_detail_counts() -> None:
    message = AIMessage(
        content="answer",
        response_metadata={
            "token_usage": {
                "prompt_tokens": 80,
                "completion_tokens": 20,
                "total_tokens": 100,
                "completion_tokens_details": {"reasoning_tokens": -1},
            }
        },
    )

    usage = usage_from_provider_metadata(message, max_output_tokens=100)

    assert usage is None


def test_usage_from_openai_response_metadata_rejects_detail_counts_above_parent_counts() -> None:
    message = AIMessage(
        content="answer",
        response_metadata={
            "token_usage": {
                "prompt_tokens": 80,
                "completion_tokens": 20,
                "total_tokens": 100,
                "completion_tokens_details": {"reasoning_tokens": 21},
            }
        },
    )

    usage = usage_from_provider_metadata(message, max_output_tokens=100)

    assert usage is None


def test_usage_from_serialized_openai_response_metadata_supports_token_usage_shape() -> None:
    message = {
        "content": "answer",
        "response_metadata": {
            "token_usage": {
                "prompt_tokens": 75,
                "completion_tokens": 15,
                "prompt_tokens_details": {"cached_tokens": 9},
                "completion_tokens_details": {"reasoning_tokens": 4},
            }
        },
    }

    usage = usage_from_provider_metadata(message, max_output_tokens=100)

    assert usage == TokenUsage(
        input_tokens=75,
        output_tokens=15,
        max_output_tokens=100,
        cached_tokens=9,
        reasoning_tokens=4,
    )


async def test_run_once_uses_provider_usage_metadata_before_estimated_counts() -> None:
    result = await run_once(
        "hello",
        Settings(max_output_tokens=100),
        graph=ProviderUsageGraph(),
    )

    assert result.token_usage == TokenUsage(
        input_tokens=120,
        output_tokens=35,
        max_output_tokens=100,
        cached_tokens=42,
        reasoning_tokens=7,
    )


class ProviderUsageGraph:
    async def ainvoke(
        self,
        state: dict[str, object],
        config: dict[str, object],
    ) -> dict[str, object]:
        _ = state, config
        return {
            "response_text": "answer",
            "messages": [
                AIMessage(
                    content="answer",
                    usage_metadata={
                        "input_tokens": 120,
                        "output_tokens": 35,
                        "total_tokens": 155,
                        "input_token_details": {"cache_read": 42},
                        "output_token_details": {"reasoning": 7},
                    },
                )
            ],
        }
