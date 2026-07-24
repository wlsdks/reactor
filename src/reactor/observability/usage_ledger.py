from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import cast

from reactor.kernel.ids import new_id
from reactor.observability.pricing import SettlementCostCalculator, quantize_money


@dataclass(frozen=True)
class UsageLedgerRecord:
    tenant_id: str
    run_id: str
    provider: str
    model: str
    step_type: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usd: Decimal
    id: str = field(default_factory=lambda: new_id("usage"))
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def validate(self) -> None:
        if not self.id.strip():
            raise ValueError("id is required")
        if not self.tenant_id.strip():
            raise ValueError("tenant_id is required")
        if not self.run_id.strip():
            raise ValueError("run_id is required")
        if not self.provider.strip():
            raise ValueError("provider is required")
        if not self.model.strip():
            raise ValueError("model is required")
        if not self.step_type.strip():
            raise ValueError("step_type is required")
        token_counts = _validated_token_counts(
            self.prompt_tokens,
            self.completion_tokens,
            self.total_tokens,
            self.cached_tokens,
            self.reasoning_tokens,
        )
        if (
            min(
                *token_counts,
            )
            < 0
        ):
            raise ValueError("token counts must be >= 0")
        if (
            self.cached_tokens > self.prompt_tokens
            or self.reasoning_tokens > self.completion_tokens
        ):
            raise ValueError("detail token counts must not exceed parent counts")
        allowed_total_tokens = {
            self.prompt_tokens + self.completion_tokens,
            self.prompt_tokens + self.completion_tokens + self.reasoning_tokens,
            self.prompt_tokens
            + self.cached_tokens
            + self.completion_tokens
            + self.reasoning_tokens,
        }
        if self.total_tokens not in allowed_total_tokens:
            raise ValueError("total_tokens must match known token components")
        estimated_cost_usd = _validated_cost(self.estimated_cost_usd)
        if not estimated_cost_usd.is_finite():
            raise ValueError("estimated_cost_usd must be finite")
        if estimated_cost_usd < 0:
            raise ValueError("estimated_cost_usd must be >= 0")


def _validated_token_counts(*values: object) -> tuple[int, ...]:
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
        raise ValueError("token counts must be integers")
    return tuple(cast(int, value) for value in values)


def _validated_cost(value: object) -> Decimal:
    if not isinstance(value, Decimal):
        raise ValueError("estimated_cost_usd must be Decimal")
    return value


@dataclass(frozen=True)
class DailyUsageSummary:
    day: date
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    total_cost_usd: Decimal


@dataclass(frozen=True)
class ExpensiveRunSummary:
    run_id: str
    total_tokens: int
    total_cost_usd: Decimal
    model: str
    occurred_at: datetime


@dataclass(frozen=True)
class TenantUsageSummary:
    tenant_id: str
    requests: int = 0
    tokens: int = 0
    cost_usd: Decimal = Decimal("0")


class InMemoryUsageLedger:
    def __init__(
        self,
        *,
        cost_calculator: SettlementCostCalculator | None = None,
        records: list[UsageLedgerRecord] | None = None,
    ) -> None:
        self._cost_calculator = cost_calculator
        self._records: list[UsageLedgerRecord] = []
        for record in records or []:
            self.record(record)

    def record(self, record: UsageLedgerRecord) -> UsageLedgerRecord:
        record.validate()
        enriched = self._enrich_cost(record)
        self._records.append(enriched)
        self._records.sort(key=lambda item: item.occurred_at)
        return enriched

    def by_session(self, tenant_id: str, session_id_prefix: str) -> list[UsageLedgerRecord]:
        return [
            record
            for record in self._records
            if record.tenant_id == tenant_id and record.run_id.startswith(session_id_prefix)
        ]

    def daily(self, tenant_id: str, from_time: datetime) -> list[DailyUsageSummary]:
        buckets: dict[tuple[date, str], list[UsageLedgerRecord]] = {}
        for record in self._records:
            if record.tenant_id != tenant_id or record.occurred_at < from_time:
                continue
            buckets.setdefault((record.occurred_at.date(), record.model), []).append(record)

        summaries = [
            DailyUsageSummary(
                day=day,
                model=model,
                prompt_tokens=sum(item.prompt_tokens for item in records),
                completion_tokens=sum(item.completion_tokens for item in records),
                total_tokens=sum(item.total_tokens for item in records),
                total_cost_usd=quantize_money(
                    sum((item.estimated_cost_usd for item in records), Decimal("0"))
                ),
            )
            for (day, model), records in buckets.items()
        ]
        return sorted(summaries, key=lambda item: (item.day, item.total_cost_usd), reverse=True)

    def top_expensive(
        self,
        tenant_id: str,
        from_time: datetime,
        *,
        limit: int,
    ) -> list[ExpensiveRunSummary]:
        buckets: dict[str, list[UsageLedgerRecord]] = {}
        for record in self._records:
            if record.tenant_id != tenant_id or record.occurred_at < from_time:
                continue
            buckets.setdefault(record.run_id, []).append(record)

        summaries = [
            ExpensiveRunSummary(
                run_id=run_id,
                total_tokens=sum(item.total_tokens for item in records),
                total_cost_usd=quantize_money(
                    sum((item.estimated_cost_usd for item in records), Decimal("0"))
                ),
                model=max(records, key=lambda item: item.occurred_at).model,
                occurred_at=max(item.occurred_at for item in records),
            )
            for run_id, records in buckets.items()
        ]
        return sorted(summaries, key=lambda item: item.total_cost_usd, reverse=True)[:limit]

    def current_month_usage(self, tenant_id: str, at: datetime | None = None) -> TenantUsageSummary:
        now = at or datetime.now(UTC)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        records = [
            record
            for record in self._records
            if record.tenant_id == tenant_id and month_start <= record.occurred_at <= now
        ]
        return TenantUsageSummary(
            tenant_id=tenant_id,
            requests=len({record.run_id for record in records}),
            tokens=sum(record.total_tokens for record in records),
            cost_usd=quantize_money(
                sum((record.estimated_cost_usd for record in records), Decimal("0"))
            ),
        )

    def records_between(
        self,
        tenant_id: str,
        from_time: datetime,
        to_time: datetime,
    ) -> list[UsageLedgerRecord]:
        return [
            record
            for record in self._records
            if record.tenant_id == tenant_id and from_time <= record.occurred_at < to_time
        ]

    def cost_by_model(
        self,
        tenant_id: str,
        from_time: datetime,
        to_time: datetime,
    ) -> dict[str, Decimal]:
        costs: dict[str, Decimal] = {}
        for record in self.records_between(tenant_id, from_time, to_time):
            costs[record.model] = costs.get(record.model, Decimal("0")) + record.estimated_cost_usd
        return {
            model: quantize_money(cost)
            for model, cost in sorted(costs.items(), key=lambda item: item[1], reverse=True)
        }

    def _enrich_cost(self, record: UsageLedgerRecord) -> UsageLedgerRecord:
        if record.estimated_cost_usd > 0 or self._cost_calculator is None:
            return record
        cost = self._cost_calculator.calculate(
            provider=record.provider,
            model=record.model,
            time=record.occurred_at,
            prompt_tokens=record.prompt_tokens,
            cached_tokens=record.cached_tokens,
            completion_tokens=record.completion_tokens,
            reasoning_tokens=record.reasoning_tokens,
        )
        return UsageLedgerRecord(
            id=record.id,
            tenant_id=record.tenant_id,
            run_id=record.run_id,
            provider=record.provider,
            model=record.model,
            step_type=record.step_type,
            prompt_tokens=record.prompt_tokens,
            cached_tokens=record.cached_tokens,
            completion_tokens=record.completion_tokens,
            reasoning_tokens=record.reasoning_tokens,
            total_tokens=record.total_tokens,
            estimated_cost_usd=cost,
            occurred_at=record.occurred_at,
        )
