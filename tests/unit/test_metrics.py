from __future__ import annotations

from decimal import Decimal

import pytest

from reactor.observability.metrics import record_model_usage_metrics, snapshot_sample_value


def test_record_model_usage_metrics_rejects_non_finite_cost_before_incrementing() -> None:
    provider = "test-provider"
    model = "metrics-invalid-cost"
    labels = {"provider": provider, "model": model, "type": "total"}
    before_total_tokens = snapshot_sample_value("reactor_model_tokens_total", labels)

    with pytest.raises(ValueError, match="estimated_cost_usd must be finite"):
        record_model_usage_metrics(
            provider=provider,
            model=model,
            input_tokens=1,
            output_tokens=2,
            total_tokens=3,
            estimated_cost_usd=Decimal("NaN"),
        )

    assert snapshot_sample_value("reactor_model_tokens_total", labels) == before_total_tokens


def test_record_model_usage_metrics_rejects_negative_cost_before_incrementing() -> None:
    provider = "test-provider"
    model = "metrics-negative-cost"
    labels = {"provider": provider, "model": model, "type": "total"}
    before_total_tokens = snapshot_sample_value("reactor_model_tokens_total", labels)

    with pytest.raises(ValueError, match="estimated_cost_usd must be >= 0"):
        record_model_usage_metrics(
            provider=provider,
            model=model,
            input_tokens=1,
            output_tokens=2,
            total_tokens=3,
            estimated_cost_usd=Decimal("-0.01"),
        )

    assert snapshot_sample_value("reactor_model_tokens_total", labels) == before_total_tokens


def test_record_model_usage_metrics_rejects_malformed_cost_before_incrementing() -> None:
    provider = "test-provider"
    model = "metrics-malformed-cost"
    labels = {"provider": provider, "model": model, "type": "total"}
    before_total_tokens = snapshot_sample_value("reactor_model_tokens_total", labels)

    with pytest.raises(ValueError, match="estimated_cost_usd must be Decimal"):
        record_model_usage_metrics(
            provider=provider,
            model=model,
            input_tokens=1,
            output_tokens=2,
            total_tokens=3,
            estimated_cost_usd=0.01,  # type: ignore[arg-type]
        )

    assert snapshot_sample_value("reactor_model_tokens_total", labels) == before_total_tokens


def test_record_model_usage_metrics_rejects_negative_token_count_before_incrementing() -> None:
    provider = "test-provider"
    model = "metrics-negative-tokens"
    input_labels = {"provider": provider, "model": model, "type": "input"}
    before_input_tokens = snapshot_sample_value("reactor_model_tokens_total", input_labels)

    with pytest.raises(ValueError, match="token counts must be >= 0"):
        record_model_usage_metrics(
            provider=provider,
            model=model,
            input_tokens=1,
            output_tokens=-1,
            total_tokens=0,
            estimated_cost_usd=Decimal("0"),
        )

    assert snapshot_sample_value("reactor_model_tokens_total", input_labels) == before_input_tokens


def test_record_model_usage_metrics_rejects_fractional_token_count_before_incrementing() -> None:
    provider = "test-provider"
    model = "metrics-fractional-tokens"
    input_labels = {"provider": provider, "model": model, "type": "input"}
    before_input_tokens = snapshot_sample_value("reactor_model_tokens_total", input_labels)

    with pytest.raises(ValueError, match="token counts must be integers"):
        record_model_usage_metrics(
            provider=provider,
            model=model,
            input_tokens=1.5,  # type: ignore[arg-type]
            output_tokens=2.5,  # type: ignore[arg-type]
            total_tokens=4,
            estimated_cost_usd=Decimal("0"),
        )

    assert snapshot_sample_value("reactor_model_tokens_total", input_labels) == before_input_tokens


def test_record_model_usage_metrics_rejects_total_token_mismatch_before_incrementing() -> None:
    provider = "test-provider"
    model = "metrics-token-mismatch"
    input_labels = {"provider": provider, "model": model, "type": "input"}
    before_input_tokens = snapshot_sample_value("reactor_model_tokens_total", input_labels)

    with pytest.raises(ValueError, match="total_tokens must match input_tokens \\+ output_tokens"):
        record_model_usage_metrics(
            provider=provider,
            model=model,
            input_tokens=1,
            output_tokens=2,
            total_tokens=99,
            estimated_cost_usd=Decimal("0"),
        )

    assert snapshot_sample_value("reactor_model_tokens_total", input_labels) == before_input_tokens
