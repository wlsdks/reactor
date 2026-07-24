from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from reactor.core.settings import Settings
from reactor.observability.pricing import ModelPricing
from reactor.providers.model_registry import (
    RegisteredModel,
    latest_effective_pricing,
    list_registered_models,
    list_registered_providers,
)


async def test_registered_models_fall_back_to_configured_default_without_pricing_store() -> None:
    models = await list_registered_models(
        Settings(default_model_provider="openai", default_model="gpt-5-mini")
    )

    assert len(models) == 1
    assert models[0].name == "gpt-5-mini"
    assert models[0].provider == "openai"
    assert models[0].input_price_per_million_tokens == Decimal("0")
    assert models[0].is_default is True


async def test_registered_models_use_latest_effective_pricing_and_keep_default_marker() -> None:
    now = datetime(2026, 6, 26, tzinfo=UTC)
    settings = Settings(default_model_provider="openai", default_model="gpt-5-mini")

    models = await list_registered_models(
        settings,
        pricing_store_factory=lambda: FakePricingStore(
            [
                pricing("old", "openai", "gpt-5-mini", now - timedelta(days=10), "1.00"),
                pricing("new", "openai", "gpt-5-mini", now - timedelta(days=1), "2.00"),
                pricing("future", "openai", "gpt-5-mini", now + timedelta(days=1), "9.00"),
                pricing("alt", "anthropic", "claude-sonnet-5", now - timedelta(days=1), "3.00"),
            ]
        ),
        now=now,
    )

    assert [(model.provider, model.name) for model in models] == [
        ("anthropic", "claude-sonnet-5"),
        ("openai", "gpt-5-mini"),
    ]
    assert models[1].input_price_per_million_tokens == Decimal("2.00")
    assert models[1].is_default is True


def test_latest_effective_pricing_filters_expired_rows() -> None:
    now = datetime(2026, 6, 26, tzinfo=UTC)
    rows = [
        pricing(
            "expired",
            "openai",
            "gpt-5-mini",
            now - timedelta(days=10),
            "1.00",
            effective_to=now - timedelta(days=1),
        ),
        pricing("current", "openai", "gpt-5-mini", now - timedelta(days=2), "2.00"),
    ]

    assert [row.id for row in latest_effective_pricing(rows, now)] == ["current"]


def test_registered_providers_deduplicates_and_prefers_default_provider() -> None:
    now = datetime(2026, 6, 26, tzinfo=UTC)
    rows = latest_effective_pricing(
        [
            pricing("primary", "openai", "gpt-5-mini", now, "1.00"),
            pricing("alt", "openai", "gpt-5", now, "2.00"),
        ],
        now,
    )

    models = [
        (
            row.provider,
            row.model,
            row.model == "gpt-5",
        )
        for row in rows
    ]

    providers = list_registered_providers(
        [
            RegisteredModel(
                name=model,
                provider=provider,
                input_price_per_million_tokens=Decimal("0"),
                output_price_per_million_tokens=Decimal("0"),
                is_default=is_default,
            )
            for provider, model, is_default in models
        ]
    )

    assert len(providers) == 1
    assert providers[0].name == "openai"
    assert providers[0].is_default is True


class FakePricingStore:
    def __init__(self, rows: list[ModelPricing]) -> None:
        self.rows = rows

    async def find_all(self) -> list[ModelPricing]:
        return self.rows


def pricing(
    pricing_id: str,
    provider: str,
    model: str,
    effective_from: datetime,
    prompt_price: str,
    *,
    effective_to: datetime | None = None,
) -> ModelPricing:
    return ModelPricing(
        id=pricing_id,
        provider=provider,
        model=model,
        prompt_price_per_1m=Decimal(prompt_price),
        completion_price_per_1m=Decimal("10.00"),
        effective_from=effective_from,
        effective_to=effective_to,
    )
