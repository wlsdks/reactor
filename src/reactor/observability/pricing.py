from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol

from reactor.kernel.ids import new_id

ONE_MILLION = Decimal("1000000")
MONEY_SCALE = Decimal("0.00000001")


@dataclass(frozen=True)
class ModelPricing:
    provider: str
    model: str
    id: str = field(default_factory=lambda: new_id("pricing"))
    prompt_price_per_1m: Decimal = Decimal("0")
    completion_price_per_1m: Decimal = Decimal("0")
    cached_input_price_per_1m: Decimal = Decimal("0")
    reasoning_price_per_1m: Decimal = Decimal("0")
    batch_prompt_price_per_1m: Decimal = Decimal("0")
    batch_completion_price_per_1m: Decimal = Decimal("0")
    effective_from: datetime = field(default_factory=lambda: datetime.now(UTC))
    effective_to: datetime | None = None

    def is_effective_at(self, at: datetime) -> bool:
        return self.effective_from <= at and (self.effective_to is None or self.effective_to > at)

    def validate(self) -> None:
        if not self.id.strip():
            raise ValueError("id is required")
        if not self.provider.strip():
            raise ValueError("provider is required")
        if not self.model.strip():
            raise ValueError("model is required")
        for label, value in (
            ("prompt_price_per_1m", self.prompt_price_per_1m),
            ("completion_price_per_1m", self.completion_price_per_1m),
            ("cached_input_price_per_1m", self.cached_input_price_per_1m),
            ("reasoning_price_per_1m", self.reasoning_price_per_1m),
            ("batch_prompt_price_per_1m", self.batch_prompt_price_per_1m),
            ("batch_completion_price_per_1m", self.batch_completion_price_per_1m),
        ):
            price = _validated_model_price(label, value)
            if not price.is_finite():
                raise ValueError(f"{label} must be finite")
            if price < 0:
                raise ValueError(f"{label} must be >= 0")
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise ValueError("effective_to must be after effective_from")


class ModelPricingStore(Protocol):
    def find_effective(self, provider: str, model: str, at: datetime) -> ModelPricing | None: ...

    def find_all(self) -> list[ModelPricing]: ...

    def save(self, pricing: ModelPricing) -> ModelPricing: ...

    def delete(self, pricing_id: str) -> bool: ...


class InMemoryModelPricingStore:
    def __init__(self, pricings: list[ModelPricing] | None = None) -> None:
        self._pricings: dict[str, ModelPricing] = {}
        for pricing in pricings or []:
            self.save(pricing)

    def find_effective(self, provider: str, model: str, at: datetime) -> ModelPricing | None:
        candidates = [
            pricing
            for pricing in self._pricings.values()
            if pricing.provider == provider
            and pricing.model == model
            and pricing.is_effective_at(at)
        ]
        return max(candidates, key=lambda pricing: pricing.effective_from, default=None)

    def find_all(self) -> list[ModelPricing]:
        return sorted(
            self._pricings.values(),
            key=lambda pricing: pricing.effective_from,
            reverse=True,
        )

    def save(self, pricing: ModelPricing) -> ModelPricing:
        pricing.validate()
        self._pricings[pricing.id] = pricing
        return pricing

    def delete(self, pricing_id: str) -> bool:
        return self._pricings.pop(pricing_id, None) is not None


class SettlementCostCalculator:
    def __init__(self, pricing_store: ModelPricingStore) -> None:
        self._pricing_store = pricing_store

    def calculate(
        self,
        *,
        provider: str,
        model: str,
        time: datetime,
        prompt_tokens: int,
        cached_tokens: int = 0,
        completion_tokens: int,
        reasoning_tokens: int = 0,
    ) -> Decimal:
        token_counts = _validated_token_counts(
            prompt_tokens,
            cached_tokens,
            completion_tokens,
            reasoning_tokens,
        )
        prompt_tokens, cached_tokens, completion_tokens, reasoning_tokens = token_counts
        if min(prompt_tokens, cached_tokens, completion_tokens, reasoning_tokens) < 0:
            raise ValueError("token counts must be >= 0")
        if cached_tokens > prompt_tokens or reasoning_tokens > completion_tokens:
            raise ValueError("detail token counts must not exceed parent counts")
        pricing = self._pricing_store.find_effective(provider, model, time)
        if pricing is None:
            return Decimal("0.00000000")
        uncached_prompt = max(prompt_tokens - cached_tokens, 0)
        cost = (
            price_per_tokens(uncached_prompt, pricing.prompt_price_per_1m)
            + price_per_tokens(cached_tokens, pricing.cached_input_price_per_1m)
            + price_per_tokens(completion_tokens, pricing.completion_price_per_1m)
            + price_per_tokens(reasoning_tokens, pricing.reasoning_price_per_1m)
        )
        return quantize_money(cost)


def price_per_tokens(tokens: int, price_per_1m: Decimal) -> Decimal:
    tokens = _validated_token_count(tokens)
    price_per_1m = _validated_model_price("price_per_1m", price_per_1m)
    if tokens < 0:
        raise ValueError("tokens must be >= 0")
    if not price_per_1m.is_finite():
        raise ValueError("price_per_1m must be finite")
    if price_per_1m < 0:
        raise ValueError("price_per_1m must be >= 0")
    if tokens == 0:
        return Decimal("0")
    return Decimal(tokens) * price_per_1m / ONE_MILLION


def _validated_token_count(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("tokens must be integers")
    return value


def _validated_token_counts(*values: object) -> tuple[int, ...]:
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
        raise ValueError("token counts must be integers")
    return tuple(value for value in values if isinstance(value, int))


def _validated_model_price(label: str, value: object) -> Decimal:
    if not isinstance(value, Decimal):
        raise ValueError(f"{label} must be Decimal")
    return value


def quantize_money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_SCALE, rounding=ROUND_HALF_UP)
