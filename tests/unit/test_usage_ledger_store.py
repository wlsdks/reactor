from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy.dialects import postgresql

from reactor.observability.pricing import ModelPricing
from reactor.observability.usage_ledger import UsageLedgerRecord
from reactor.persistence.models import Base
from reactor.persistence.usage_ledger_store import (
    build_model_pricing_effective,
    build_model_pricing_upsert,
    build_usage_between,
    build_usage_by_session,
    build_usage_cost_by_model,
    build_usage_current_month,
    build_usage_daily,
    build_usage_ledger_insert,
    build_usage_top_expensive,
)

NOW = datetime(2026, 6, 26, 12, 0, tzinfo=UTC)


def test_usage_ledger_models_are_registered_in_metadata() -> None:
    assert "model_pricing" in Base.metadata.tables
    assert "usage_ledger" in Base.metadata.tables
    pricing_indexes = Base.metadata.tables["model_pricing"].indexes
    ledger_indexes = Base.metadata.tables["usage_ledger"].indexes

    assert "ix_model_pricing_effective" in {index.name for index in pricing_indexes}
    assert "ix_usage_ledger_tenant_occurred" in {index.name for index in ledger_indexes}
    assert "ix_usage_ledger_tenant_run" in {index.name for index in ledger_indexes}


def test_usage_ledger_store_queries_are_tenant_scoped_and_postgres_compatible() -> None:
    pricing = ModelPricing(
        id="pricing_1",
        provider="openai",
        model="gpt-5-mini",
        prompt_price_per_1m=Decimal("0.15"),
        completion_price_per_1m=Decimal("0.60"),
        effective_from=NOW - timedelta(days=1),
    )
    record = UsageLedgerRecord(
        id="usage_1",
        tenant_id="tenant_1",
        run_id="session-a-turn-1",
        provider="openai",
        model="gpt-5-mini",
        step_type="model",
        prompt_tokens=1000,
        completion_tokens=200,
        total_tokens=1200,
        estimated_cost_usd=Decimal("0.00027000"),
        occurred_at=NOW,
    )

    pricing_upsert = str(build_model_pricing_upsert(pricing).compile(dialect=postgresql.dialect()))
    pricing_effective = build_model_pricing_effective("openai", "gpt-5-mini", NOW).compile(
        dialect=postgresql.dialect()
    )
    usage_insert = str(build_usage_ledger_insert(record).compile(dialect=postgresql.dialect()))
    by_session = build_usage_by_session("tenant_1", "session-a").compile(
        dialect=postgresql.dialect()
    )
    daily = build_usage_daily("tenant_1", NOW - timedelta(days=7)).compile(
        dialect=postgresql.dialect()
    )
    top = build_usage_top_expensive("tenant_1", NOW - timedelta(days=7), 10).compile(
        dialect=postgresql.dialect()
    )
    current_month = build_usage_current_month(
        "tenant_1",
        NOW.replace(day=1, hour=0, minute=0, second=0, microsecond=0),
        NOW,
    ).compile(dialect=postgresql.dialect())
    between = build_usage_between("tenant_1", NOW - timedelta(days=1), NOW).compile(
        dialect=postgresql.dialect()
    )
    cost_by_model = build_usage_cost_by_model("tenant_1", NOW - timedelta(days=1), NOW).compile(
        dialect=postgresql.dialect()
    )

    assert "model_pricing" in pricing_upsert
    assert "ON CONFLICT" in pricing_upsert
    assert pricing_effective.params["provider_1"] == "openai"
    assert pricing_effective.params["model_1"] == "gpt-5-mini"
    assert "usage_ledger" in usage_insert
    assert by_session.params["tenant_id_1"] == "tenant_1"
    assert by_session.params["run_id_1"] == "session-a%"
    assert daily.params["tenant_id_1"] == "tenant_1"
    assert "GROUP BY date(usage_ledger.occurred_at)" in str(daily)
    assert top.params["tenant_id_1"] == "tenant_1"
    assert top.params["param_1"] == 10
    assert current_month.params["tenant_id_1"] == "tenant_1"
    assert "count(distinct(usage_ledger.run_id))" in str(current_month)
    assert "sum(usage_ledger.total_tokens)" in str(current_month)
    assert between.params["tenant_id_1"] == "tenant_1"
    assert "ORDER BY usage_ledger.occurred_at ASC" in str(between)
    assert cost_by_model.params["tenant_id_1"] == "tenant_1"
    assert "GROUP BY usage_ledger.model" in str(cost_by_model)
