from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from reactor.observability.pricing import (
    InMemoryModelPricingStore,
    ModelPricing,
    SettlementCostCalculator,
    price_per_tokens,
)
from reactor.observability.usage_ledger import (
    InMemoryUsageLedger,
    UsageLedgerRecord,
)

NOW = datetime(2026, 6, 26, 12, 0, tzinfo=UTC)


def test_pricing_store_finds_latest_effective_price() -> None:
    store = InMemoryModelPricingStore()
    older = ModelPricing(
        id="pricing_old",
        provider="openai",
        model="gpt-5-mini",
        prompt_price_per_1m=Decimal("0.15"),
        completion_price_per_1m=Decimal("0.60"),
        effective_from=NOW - timedelta(days=10),
    )
    newer = ModelPricing(
        id="pricing_new",
        provider="openai",
        model="gpt-5-mini",
        prompt_price_per_1m=Decimal("0.20"),
        completion_price_per_1m=Decimal("0.80"),
        effective_from=NOW - timedelta(days=1),
    )

    store.save(older)
    store.save(newer)

    assert store.find_effective("openai", "gpt-5-mini", NOW) == newer


def test_settlement_cost_calculator_uses_per_million_precision_and_cached_tokens() -> None:
    store = InMemoryModelPricingStore()
    store.save(
        ModelPricing(
            id="pricing_1",
            provider="openai",
            model="gpt-5-mini",
            prompt_price_per_1m=Decimal("0.15"),
            completion_price_per_1m=Decimal("0.60"),
            cached_input_price_per_1m=Decimal("0.075"),
            reasoning_price_per_1m=Decimal("2.00"),
            effective_from=NOW - timedelta(days=1),
        )
    )
    calculator = SettlementCostCalculator(store)

    cost = calculator.calculate(
        provider="openai",
        model="gpt-5-mini",
        time=NOW,
        prompt_tokens=1000,
        cached_tokens=400,
        completion_tokens=200,
        reasoning_tokens=50,
    )

    assert cost == Decimal("0.00034000")


def test_price_per_tokens_rejects_negative_token_count() -> None:
    with pytest.raises(ValueError, match="tokens must be >= 0"):
        price_per_tokens(-1, Decimal("0.15"))


def test_price_per_tokens_rejects_fractional_token_count() -> None:
    with pytest.raises(ValueError, match="tokens must be integers"):
        price_per_tokens(1.5, Decimal("0.15"))  # type: ignore[arg-type]


def test_price_per_tokens_rejects_negative_price() -> None:
    with pytest.raises(ValueError, match="price_per_1m must be >= 0"):
        price_per_tokens(1, Decimal("-0.15"))


def test_price_per_tokens_rejects_non_finite_price() -> None:
    with pytest.raises(ValueError, match="price_per_1m must be finite"):
        price_per_tokens(1, Decimal("NaN"))


def test_price_per_tokens_rejects_malformed_price() -> None:
    with pytest.raises(ValueError, match="price_per_1m must be Decimal"):
        price_per_tokens(1, 0.15)  # type: ignore[arg-type]


def test_pricing_store_rejects_non_finite_model_price() -> None:
    store = InMemoryModelPricingStore()
    pricing = ModelPricing(
        id="pricing_bad",
        provider="openai",
        model="gpt-5-mini",
        prompt_price_per_1m=Decimal("NaN"),
        effective_from=NOW - timedelta(days=1),
    )

    with pytest.raises(ValueError, match="prompt_price_per_1m must be finite"):
        store.save(pricing)


def test_pricing_store_rejects_malformed_model_price() -> None:
    store = InMemoryModelPricingStore()
    pricing = ModelPricing(
        id="pricing_bad",
        provider="openai",
        model="gpt-5-mini",
        prompt_price_per_1m=0.15,  # type: ignore[arg-type]
        effective_from=NOW - timedelta(days=1),
    )

    with pytest.raises(ValueError, match="prompt_price_per_1m must be Decimal"):
        store.save(pricing)


def test_settlement_cost_calculator_rejects_detail_counts_above_parent_counts() -> None:
    store = InMemoryModelPricingStore()
    store.save(
        ModelPricing(
            id="pricing_1",
            provider="openai",
            model="gpt-5-mini",
            prompt_price_per_1m=Decimal("0.15"),
            completion_price_per_1m=Decimal("0.60"),
            cached_input_price_per_1m=Decimal("0.075"),
            reasoning_price_per_1m=Decimal("2.00"),
            effective_from=NOW - timedelta(days=1),
        )
    )
    calculator = SettlementCostCalculator(store)

    with pytest.raises(ValueError, match="detail token counts must not exceed parent counts"):
        calculator.calculate(
            provider="openai",
            model="gpt-5-mini",
            time=NOW,
            prompt_tokens=10,
            cached_tokens=11,
            completion_tokens=5,
            reasoning_tokens=0,
        )


def test_settlement_cost_calculator_rejects_negative_token_counts() -> None:
    store = InMemoryModelPricingStore()
    store.save(
        ModelPricing(
            id="pricing_1",
            provider="openai",
            model="gpt-5-mini",
            prompt_price_per_1m=Decimal("0.15"),
            completion_price_per_1m=Decimal("0.60"),
            cached_input_price_per_1m=Decimal("0.075"),
            reasoning_price_per_1m=Decimal("2.00"),
            effective_from=NOW - timedelta(days=1),
        )
    )
    calculator = SettlementCostCalculator(store)

    with pytest.raises(ValueError, match="token counts must be >= 0"):
        calculator.calculate(
            provider="openai",
            model="gpt-5-mini",
            time=NOW,
            prompt_tokens=10,
            cached_tokens=-1,
            completion_tokens=5,
            reasoning_tokens=0,
        )


def test_settlement_cost_calculator_rejects_fractional_tokens_without_pricing() -> None:
    calculator = SettlementCostCalculator(InMemoryModelPricingStore())

    with pytest.raises(ValueError, match="token counts must be integers"):
        calculator.calculate(
            provider="openai",
            model="gpt-5-mini",
            time=NOW,
            prompt_tokens=10.5,  # type: ignore[arg-type]
            cached_tokens=0,
            completion_tokens=5,
            reasoning_tokens=0,
        )


def test_usage_ledger_enriches_missing_cost_and_queries_session_daily_and_top() -> None:
    pricing_store = InMemoryModelPricingStore()
    pricing_store.save(
        ModelPricing(
            id="pricing_1",
            provider="openai",
            model="gpt-5-mini",
            prompt_price_per_1m=Decimal("0.15"),
            completion_price_per_1m=Decimal("0.60"),
            effective_from=NOW - timedelta(days=1),
        )
    )
    ledger = InMemoryUsageLedger(cost_calculator=SettlementCostCalculator(pricing_store))

    first = ledger.record(
        UsageLedgerRecord(
            id="usage_1",
            tenant_id="tenant_1",
            run_id="session-a-turn-1",
            provider="openai",
            model="gpt-5-mini",
            step_type="model",
            prompt_tokens=1000,
            completion_tokens=1000,
            total_tokens=2000,
            estimated_cost_usd=Decimal("0"),
            occurred_at=NOW,
        )
    )
    ledger.record(
        UsageLedgerRecord(
            id="usage_2",
            tenant_id="tenant_1",
            run_id="session-b-turn-1",
            provider="openai",
            model="gpt-5-mini",
            step_type="model",
            prompt_tokens=5000,
            completion_tokens=5000,
            total_tokens=10000,
            estimated_cost_usd=Decimal("0.01000000"),
            occurred_at=NOW + timedelta(minutes=1),
        )
    )

    assert first.estimated_cost_usd == Decimal("0.00075000")
    assert [row.run_id for row in ledger.by_session("tenant_1", "session-a")] == [
        "session-a-turn-1"
    ]
    assert ledger.daily("tenant_1", NOW - timedelta(days=1))[0].total_cost_usd == Decimal(
        "0.01075000"
    )
    assert ledger.top_expensive("tenant_1", NOW - timedelta(days=1), limit=1)[0].run_id == (
        "session-b-turn-1"
    )


def test_usage_ledger_rejects_total_token_mismatch() -> None:
    record = UsageLedgerRecord(
        id="usage_bad",
        tenant_id="tenant_1",
        run_id="run_1",
        provider="openai",
        model="gpt-5-mini",
        step_type="model",
        prompt_tokens=100,
        completion_tokens=25,
        total_tokens=999,
        estimated_cost_usd=Decimal("0"),
        occurred_at=NOW,
    )

    with pytest.raises(ValueError, match="total_tokens must match known token components"):
        record.validate()


def test_usage_ledger_rejects_fractional_token_counts() -> None:
    record = UsageLedgerRecord(
        id="usage_bad",
        tenant_id="tenant_1",
        run_id="run_1",
        provider="openai",
        model="gpt-5-mini",
        step_type="model",
        prompt_tokens=100.5,  # type: ignore[arg-type]
        completion_tokens=24.5,  # type: ignore[arg-type]
        total_tokens=125,
        estimated_cost_usd=Decimal("0"),
        occurred_at=NOW,
    )

    with pytest.raises(ValueError, match="token counts must be integers"):
        record.validate()


def test_usage_ledger_rejects_non_finite_estimated_cost() -> None:
    record = UsageLedgerRecord(
        id="usage_bad",
        tenant_id="tenant_1",
        run_id="run_1",
        provider="openai",
        model="gpt-5-mini",
        step_type="model",
        prompt_tokens=100,
        completion_tokens=25,
        total_tokens=125,
        estimated_cost_usd=Decimal("NaN"),
        occurred_at=NOW,
    )

    with pytest.raises(ValueError, match="estimated_cost_usd must be finite"):
        record.validate()


def test_usage_ledger_rejects_malformed_estimated_cost() -> None:
    record = UsageLedgerRecord(
        id="usage_bad",
        tenant_id="tenant_1",
        run_id="run_1",
        provider="openai",
        model="gpt-5-mini",
        step_type="model",
        prompt_tokens=100,
        completion_tokens=25,
        total_tokens=125,
        estimated_cost_usd=0.01,  # type: ignore[arg-type]
        occurred_at=NOW,
    )

    with pytest.raises(ValueError, match="estimated_cost_usd must be Decimal"):
        record.validate()


def test_usage_ledger_rejects_detail_counts_above_parent_counts() -> None:
    record = UsageLedgerRecord(
        id="usage_bad",
        tenant_id="tenant_1",
        run_id="run_1",
        provider="openai",
        model="gpt-5-mini",
        step_type="model",
        prompt_tokens=10,
        cached_tokens=11,
        completion_tokens=5,
        reasoning_tokens=0,
        total_tokens=26,
        estimated_cost_usd=Decimal("0"),
        occurred_at=NOW,
    )

    with pytest.raises(ValueError, match="detail token counts must not exceed parent counts"):
        record.validate()
