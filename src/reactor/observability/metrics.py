from __future__ import annotations

from decimal import Decimal

from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, Counter, generate_latest
from starlette.responses import Response

RUNS_CREATED = Counter("reactor_runs_total", "Total Reactor runs.", ["status"])
MODEL_TOKENS = Counter(
    "reactor_model_tokens_total",
    "Total model tokens recorded by Reactor.",
    ["provider", "model", "type"],
)
MODEL_COST_USD = Counter(
    "reactor_model_cost_usd_total",
    "Estimated model cost recorded by Reactor in USD.",
    ["provider", "model"],
)

REACTOR_PROMETHEUS_METRIC_NAMES = (
    "reactor_runs_total",
    "reactor_model_tokens_total",
    "reactor_model_cost_usd_total",
)


def reactor_prometheus_metric_names() -> list[str]:
    return list(REACTOR_PROMETHEUS_METRIC_NAMES)


def record_model_usage_metrics(
    *,
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    total_tokens: int,
    estimated_cost_usd: Decimal,
) -> None:
    token_counts = _validated_token_counts(input_tokens, output_tokens, total_tokens)
    input_tokens, output_tokens, total_tokens = token_counts
    estimated_cost_usd = _validated_cost(estimated_cost_usd)
    if min(input_tokens, output_tokens, total_tokens) < 0:
        raise ValueError("token counts must be >= 0")
    if total_tokens != input_tokens + output_tokens:
        raise ValueError("total_tokens must match input_tokens + output_tokens")
    if not estimated_cost_usd.is_finite():
        raise ValueError("estimated_cost_usd must be finite")
    if estimated_cost_usd < 0:
        raise ValueError("estimated_cost_usd must be >= 0")
    MODEL_TOKENS.labels(provider=provider, model=model, type="input").inc(input_tokens)
    MODEL_TOKENS.labels(provider=provider, model=model, type="output").inc(output_tokens)
    MODEL_TOKENS.labels(provider=provider, model=model, type="total").inc(total_tokens)
    if estimated_cost_usd > 0:
        MODEL_COST_USD.labels(provider=provider, model=model).inc(float(estimated_cost_usd))
    else:
        MODEL_COST_USD.labels(provider=provider, model=model)


def _validated_token_counts(*values: object) -> tuple[int, ...]:
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
        raise ValueError("token counts must be integers")
    return tuple(value for value in values if isinstance(value, int))


def _validated_cost(value: object) -> Decimal:
    if not isinstance(value, Decimal):
        raise ValueError("estimated_cost_usd must be Decimal")
    return value


def snapshot_sample_value(name: str, labels: dict[str, str]) -> float:
    for metric in REGISTRY.collect():
        for sample in metric.samples:
            if sample.name == name and all(
                sample.labels.get(key) == value for key, value in labels.items()
            ):
                return float(sample.value)
    return 0.0


def metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
