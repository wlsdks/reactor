from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reactor.observability.pricing import ModelPricing, quantize_money
from reactor.observability.usage_ledger import (
    DailyUsageSummary,
    ExpensiveRunSummary,
    TenantUsageSummary,
    UsageLedgerRecord,
)
from reactor.persistence.models import ModelPricing as ModelPricingRow
from reactor.persistence.models import UsageLedger as UsageLedgerRow


class SqlAlchemyModelPricingStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def find_effective(self, provider: str, model: str, at: datetime) -> ModelPricing | None:
        async with self._session_factory() as session:
            row = await session.scalar(build_model_pricing_effective(provider, model, at))
        return model_pricing_from_row(row) if row is not None else None

    async def find_all(self) -> list[ModelPricing]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_model_pricing_list())
        return [model_pricing_from_row(row) for row in rows]

    async def save(self, pricing: ModelPricing) -> ModelPricing:
        pricing.validate()
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.scalar(build_model_pricing_upsert(pricing))
                if row is None:
                    raise RuntimeError("model pricing upsert did not return a row")
        return model_pricing_from_row(row)

    async def delete(self, pricing_id: str) -> bool:
        async with self._session_factory() as session:
            async with session.begin():
                deleted_id = await session.scalar(
                    delete(ModelPricingRow)
                    .where(ModelPricingRow.id == pricing_id)
                    .returning(ModelPricingRow.id)
                )
        return deleted_id is not None


class SqlAlchemyUsageLedger:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def record(self, record: UsageLedgerRecord) -> UsageLedgerRecord:
        record.validate()
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.scalar(build_usage_ledger_insert(record))
                if row is None:
                    raise RuntimeError("usage ledger insert did not return a row")
        return usage_ledger_from_row(row)

    async def by_session(self, tenant_id: str, session_id_prefix: str) -> list[UsageLedgerRecord]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_usage_by_session(tenant_id, session_id_prefix))
        return [usage_ledger_from_row(row) for row in rows]

    async def daily(self, tenant_id: str, from_time: datetime) -> list[DailyUsageSummary]:
        async with self._session_factory() as session:
            rows = await session.execute(build_usage_daily(tenant_id, from_time))
        return [daily_usage_from_row(row) for row in rows]

    async def top_expensive(
        self,
        tenant_id: str,
        from_time: datetime,
        *,
        limit: int,
    ) -> list[ExpensiveRunSummary]:
        async with self._session_factory() as session:
            rows = await session.execute(build_usage_top_expensive(tenant_id, from_time, limit))
        return [expensive_run_from_row(row) for row in rows]

    async def current_month_usage(
        self, tenant_id: str, at: datetime | None = None
    ) -> TenantUsageSummary:
        now = at or datetime.now().astimezone()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        async with self._session_factory() as session:
            row = await session.execute(build_usage_current_month(tenant_id, month_start, now))
        return tenant_usage_from_row(tenant_id, row.one())

    async def records_between(
        self,
        tenant_id: str,
        from_time: datetime,
        to_time: datetime,
    ) -> list[UsageLedgerRecord]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_usage_between(tenant_id, from_time, to_time))
        return [usage_ledger_from_row(row) for row in rows]

    async def cost_by_model(
        self,
        tenant_id: str,
        from_time: datetime,
        to_time: datetime,
    ) -> dict[str, Decimal]:
        async with self._session_factory() as session:
            rows = await session.execute(build_usage_cost_by_model(tenant_id, from_time, to_time))
        return {str(row[0]): quantize_money(Decimal(str(row[1] or "0"))) for row in rows.all()}


def build_model_pricing_effective(provider: str, model: str, at: datetime) -> Any:
    return (
        select(ModelPricingRow)
        .where(
            ModelPricingRow.provider == provider,
            ModelPricingRow.model == model,
            ModelPricingRow.effective_from <= at,
            (ModelPricingRow.effective_to.is_(None)) | (ModelPricingRow.effective_to > at),
        )
        .order_by(ModelPricingRow.effective_from.desc())
        .limit(1)
    )


def build_model_pricing_list() -> Any:
    return select(ModelPricingRow).order_by(ModelPricingRow.effective_from.desc())


def build_model_pricing_upsert(pricing: ModelPricing) -> Any:
    pricing.validate()
    return (
        insert(ModelPricingRow)
        .values(model_pricing_values(pricing))
        .on_conflict_do_update(
            index_elements=[ModelPricingRow.id],
            set_=model_pricing_values(pricing),
        )
        .returning(ModelPricingRow)
    )


def build_usage_ledger_insert(record: UsageLedgerRecord) -> Any:
    record.validate()
    return insert(UsageLedgerRow).values(usage_ledger_values(record)).returning(UsageLedgerRow)


def build_usage_by_session(tenant_id: str, session_id_prefix: str) -> Any:
    return (
        select(UsageLedgerRow)
        .where(
            UsageLedgerRow.tenant_id == tenant_id,
            UsageLedgerRow.run_id.like(f"{session_id_prefix}%"),
        )
        .order_by(UsageLedgerRow.occurred_at.asc())
    )


def build_usage_daily(tenant_id: str, from_time: datetime) -> Any:
    day = func.date(UsageLedgerRow.occurred_at).label("day")
    return (
        select(
            day,
            UsageLedgerRow.model,
            func.sum(UsageLedgerRow.prompt_tokens).label("prompt_tokens"),
            func.sum(UsageLedgerRow.completion_tokens).label("completion_tokens"),
            func.sum(UsageLedgerRow.total_tokens).label("total_tokens"),
            func.sum(UsageLedgerRow.estimated_cost_usd).label("total_cost_usd"),
        )
        .where(UsageLedgerRow.tenant_id == tenant_id, UsageLedgerRow.occurred_at >= from_time)
        .group_by(day, UsageLedgerRow.model)
        .order_by(day.desc(), func.sum(UsageLedgerRow.estimated_cost_usd).desc())
    )


def build_usage_top_expensive(tenant_id: str, from_time: datetime, limit: int) -> Any:
    occurred_at = func.max(UsageLedgerRow.occurred_at).label("occurred_at")
    return (
        select(
            UsageLedgerRow.run_id,
            func.sum(UsageLedgerRow.total_tokens).label("total_tokens"),
            func.sum(UsageLedgerRow.estimated_cost_usd).label("total_cost_usd"),
            func.max(UsageLedgerRow.model).label("model"),
            occurred_at,
        )
        .where(UsageLedgerRow.tenant_id == tenant_id, UsageLedgerRow.occurred_at >= from_time)
        .group_by(UsageLedgerRow.run_id)
        .order_by(func.sum(UsageLedgerRow.estimated_cost_usd).desc())
        .limit(max(1, min(limit, 100)))
    )


def build_usage_current_month(tenant_id: str, from_time: datetime, to_time: datetime) -> Any:
    return select(
        func.count(func.distinct(UsageLedgerRow.run_id)).label("requests"),
        func.coalesce(func.sum(UsageLedgerRow.total_tokens), 0).label("tokens"),
        func.coalesce(func.sum(UsageLedgerRow.estimated_cost_usd), 0).label("cost_usd"),
    ).where(
        UsageLedgerRow.tenant_id == tenant_id,
        UsageLedgerRow.occurred_at >= from_time,
        UsageLedgerRow.occurred_at <= to_time,
    )


def build_usage_between(tenant_id: str, from_time: datetime, to_time: datetime) -> Any:
    return (
        select(UsageLedgerRow)
        .where(
            UsageLedgerRow.tenant_id == tenant_id,
            UsageLedgerRow.occurred_at >= from_time,
            UsageLedgerRow.occurred_at < to_time,
        )
        .order_by(UsageLedgerRow.occurred_at.asc(), UsageLedgerRow.id.asc())
    )


def build_usage_cost_by_model(tenant_id: str, from_time: datetime, to_time: datetime) -> Any:
    return (
        select(
            UsageLedgerRow.model,
            func.sum(UsageLedgerRow.estimated_cost_usd).label("cost_usd"),
        )
        .where(
            UsageLedgerRow.tenant_id == tenant_id,
            UsageLedgerRow.occurred_at >= from_time,
            UsageLedgerRow.occurred_at < to_time,
        )
        .group_by(UsageLedgerRow.model)
        .order_by(func.sum(UsageLedgerRow.estimated_cost_usd).desc())
    )


def model_pricing_values(pricing: ModelPricing) -> dict[str, object]:
    return {
        "id": pricing.id,
        "provider": pricing.provider,
        "model": pricing.model,
        "prompt_price_per_1m": pricing.prompt_price_per_1m,
        "completion_price_per_1m": pricing.completion_price_per_1m,
        "cached_input_price_per_1m": pricing.cached_input_price_per_1m,
        "reasoning_price_per_1m": pricing.reasoning_price_per_1m,
        "batch_prompt_price_per_1m": pricing.batch_prompt_price_per_1m,
        "batch_completion_price_per_1m": pricing.batch_completion_price_per_1m,
        "effective_from": pricing.effective_from,
        "effective_to": pricing.effective_to,
    }


def usage_ledger_values(record: UsageLedgerRecord) -> dict[str, object]:
    return {
        "id": record.id,
        "tenant_id": record.tenant_id,
        "run_id": record.run_id,
        "provider": record.provider,
        "model": record.model,
        "step_type": record.step_type,
        "prompt_tokens": record.prompt_tokens,
        "cached_tokens": record.cached_tokens,
        "completion_tokens": record.completion_tokens,
        "reasoning_tokens": record.reasoning_tokens,
        "total_tokens": record.total_tokens,
        "estimated_cost_usd": record.estimated_cost_usd,
        "occurred_at": record.occurred_at,
    }


def model_pricing_from_row(row: ModelPricingRow) -> ModelPricing:
    return ModelPricing(
        id=row.id,
        provider=row.provider,
        model=row.model,
        prompt_price_per_1m=row.prompt_price_per_1m,
        completion_price_per_1m=row.completion_price_per_1m,
        cached_input_price_per_1m=row.cached_input_price_per_1m,
        reasoning_price_per_1m=row.reasoning_price_per_1m,
        batch_prompt_price_per_1m=row.batch_prompt_price_per_1m,
        batch_completion_price_per_1m=row.batch_completion_price_per_1m,
        effective_from=row.effective_from,
        effective_to=row.effective_to,
    )


def usage_ledger_from_row(row: UsageLedgerRow) -> UsageLedgerRecord:
    return UsageLedgerRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        run_id=row.run_id,
        provider=row.provider,
        model=row.model,
        step_type=row.step_type,
        prompt_tokens=row.prompt_tokens,
        cached_tokens=row.cached_tokens,
        completion_tokens=row.completion_tokens,
        reasoning_tokens=row.reasoning_tokens,
        total_tokens=row.total_tokens,
        estimated_cost_usd=row.estimated_cost_usd,
        occurred_at=row.occurred_at,
    )


def daily_usage_from_row(row: Sequence[object]) -> DailyUsageSummary:
    return DailyUsageSummary(
        day=parse_sql_date(row[0]),
        model=cast(str, row[1]),
        prompt_tokens=int(cast(int, row[2])),
        completion_tokens=int(cast(int, row[3])),
        total_tokens=int(cast(int, row[4])),
        total_cost_usd=quantize_money(cast(Decimal, row[5])),
    )


def tenant_usage_from_row(tenant_id: str, row: Sequence[object]) -> TenantUsageSummary:
    return TenantUsageSummary(
        tenant_id=tenant_id,
        requests=int(cast(Any, row[0] or 0)),
        tokens=int(cast(Any, row[1] or 0)),
        cost_usd=quantize_money(Decimal(str(row[2] or "0"))),
    )


def expensive_run_from_row(row: Sequence[object]) -> ExpensiveRunSummary:
    return ExpensiveRunSummary(
        run_id=cast(str, row[0]),
        total_tokens=int(cast(int, row[1])),
        total_cost_usd=quantize_money(cast(Decimal, row[2])),
        model=cast(str, row[3]),
        occurred_at=cast(datetime, row[4]),
    )


def parse_sql_date(value: object) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise TypeError(f"unsupported SQL date value: {value!r}")
