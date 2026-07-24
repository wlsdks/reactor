from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from inspect import isawaitable
from typing import Protocol

from reactor.core.settings import Settings
from reactor.observability.pricing import ModelPricing


@dataclass(frozen=True)
class RegisteredModel:
    name: str
    provider: str
    input_price_per_million_tokens: Decimal
    output_price_per_million_tokens: Decimal
    is_default: bool


class ModelPricingReader(Protocol):
    def find_all(self) -> Sequence[ModelPricing] | Awaitable[Sequence[ModelPricing]]: ...


ModelPricingStoreFactory = Callable[[], ModelPricingReader | None]


async def list_registered_models(
    settings: Settings,
    pricing_store_factory: ModelPricingStoreFactory | None = None,
    *,
    now: datetime | None = None,
) -> list[RegisteredModel]:
    effective_at = now or datetime.now(UTC)
    pricing_rows = await _load_pricing_rows(pricing_store_factory)
    if not pricing_rows:
        return [default_settings_model(settings)]

    latest_by_model = latest_effective_pricing(pricing_rows, effective_at)
    models = [
        RegisteredModel(
            name=pricing.model,
            provider=pricing.provider,
            input_price_per_million_tokens=pricing.prompt_price_per_1m,
            output_price_per_million_tokens=pricing.completion_price_per_1m,
            is_default=is_default_model(settings, pricing.provider, pricing.model),
        )
        for pricing in latest_by_model
    ]
    if any(model.is_default for model in models):
        return models
    return [default_settings_model(settings), *models]


def list_registered_providers(models: Sequence[RegisteredModel]) -> list[RegisteredModel]:
    providers: dict[str, RegisteredModel] = {}
    for model in models:
        current = providers.get(model.provider)
        if current is None or model.is_default:
            providers[model.provider] = RegisteredModel(
                name=model.provider,
                provider=model.provider,
                input_price_per_million_tokens=Decimal("0"),
                output_price_per_million_tokens=Decimal("0"),
                is_default=model.is_default,
            )
    return sorted(providers.values(), key=lambda model: (not model.is_default, model.name))


def latest_effective_pricing(
    rows: Sequence[ModelPricing],
    effective_at: datetime,
) -> list[ModelPricing]:
    latest: dict[tuple[str, str], ModelPricing] = {}
    for row in rows:
        if row.effective_from > effective_at:
            continue
        if row.effective_to is not None and row.effective_to <= effective_at:
            continue
        key = (row.provider, row.model)
        current = latest.get(key)
        if current is None or row.effective_from > current.effective_from:
            latest[key] = row
    return sorted(latest.values(), key=lambda row: (row.provider, row.model))


def default_settings_model(settings: Settings) -> RegisteredModel:
    return RegisteredModel(
        name=settings.default_model,
        provider=settings.default_model_provider,
        input_price_per_million_tokens=Decimal("0"),
        output_price_per_million_tokens=Decimal("0"),
        is_default=True,
    )


def is_default_model(settings: Settings, provider: str, model: str) -> bool:
    return provider == settings.default_model_provider and model == settings.default_model


async def _load_pricing_rows(
    pricing_store_factory: ModelPricingStoreFactory | None,
) -> Sequence[ModelPricing]:
    if pricing_store_factory is None:
        return []
    store = pricing_store_factory()
    if store is None:
        return []
    result = store.find_all()
    if isawaitable(result):
        return await result
    return result
