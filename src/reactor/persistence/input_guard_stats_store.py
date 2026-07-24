from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reactor.guards.input import InputGuardMetricRecord
from reactor.persistence.models import MetricGuardEvent

ALLOWED_ACTION = "allowed"
REJECTED_ACTION = "rejected"
ERROR_ACTION = "error"


@dataclass(frozen=True)
class InputGuardMetricMigrationRecord:
    time: datetime
    tenant_id: str | None
    user_id: str | None
    channel: str | None
    stage: str
    category: str | None
    reason_class: str | None
    reason_detail: str | None
    is_output_guard: bool
    action: str

    def validate(self) -> None:
        if not self.stage.strip():
            raise ValueError("stage is required")
        if self.action not in {ALLOWED_ACTION, REJECTED_ACTION, ERROR_ACTION}:
            raise ValueError(f"unsupported guard action: {self.action}")


class SqlAlchemyInputGuardMetricSink:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def record(self, record: InputGuardMetricRecord) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(build_input_guard_metric_insert(record))

    async def save_metric(self, record: InputGuardMetricMigrationRecord) -> None:
        record.validate()
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(build_input_guard_metric_migration_insert(record))


class SqlAlchemyInputGuardStatsQuery:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock or (lambda: datetime.now().astimezone())

    async def get_stats(
        self,
        *,
        period_hours: int = 24,
        tenant_id: str | None = None,
    ) -> dict[str, object]:
        hours = max(1, min(period_hours, 168))
        since = self._clock() - timedelta(hours=hours)
        async with self._session_factory() as session:
            totals_result = await session.execute(build_input_guard_totals(since, tenant_id))
            stage_result = await session.execute(build_input_guard_stage_counts(since, tenant_id))

            totals = totals_from_rows(totals_result.mappings().all())
            stage_actions: dict[str, dict[str, int]] = {}
            for row in stage_result.mappings().all():
                stage = str(row["stage"] or "unknown")
                action = str(row["action"] or "")
                count = int(row["count"] or 0)
                stage_actions.setdefault(stage, {})[action] = count

            by_stage: list[dict[str, object]] = []
            for stage, actions in sorted(
                stage_actions.items(),
                key=lambda item: sum(item[1].values()),
                reverse=True,
            ):
                reason_rows = await session.execute(
                    build_input_guard_top_reasons(since, stage=stage, tenant_id=tenant_id)
                )
                by_stage.append(stage_stats(stage, actions, reason_rows.mappings().all()))

        total_requests = totals[ALLOWED_ACTION] + totals[REJECTED_ACTION] + totals[ERROR_ACTION]
        return {
            "periodHours": hours,
            "totalRequests": total_requests,
            "totalAllowed": totals[ALLOWED_ACTION],
            "totalRejected": totals[REJECTED_ACTION],
            "totalErrors": totals[ERROR_ACTION],
            "blockRate": totals[REJECTED_ACTION] / total_requests if total_requests else 0.0,
            "byStage": by_stage,
        }

    async def list_audits(
        self,
        *,
        limit: int = 200,
        tenant_id: str | None = None,
        action: str | None = None,
    ) -> list[Mapping[str, Any]]:
        async with self._session_factory() as session:
            result = await session.execute(
                build_input_guard_audit_query(limit=limit, tenant_id=tenant_id, action=action)
            )
            return [cast(Mapping[str, Any], row) for row in result.mappings().all()]


def build_input_guard_metric_insert(record: InputGuardMetricRecord) -> Any:
    return insert(MetricGuardEvent).values(
        tenant_id=record.tenant_id,
        user_id=record.user_id,
        channel=record.channel,
        stage=record.stage,
        category=record.category,
        reason_class=record.reason_class,
        reason_detail=(record.reason_detail[:500] if record.reason_detail is not None else None),
        is_output_guard=False,
        action=record.action,
    )


def build_input_guard_metric_migration_insert(record: InputGuardMetricMigrationRecord) -> Any:
    record.validate()
    return insert(MetricGuardEvent).values(
        time=record.time,
        tenant_id=record.tenant_id,
        user_id=record.user_id,
        channel=record.channel,
        stage=record.stage,
        category=record.category,
        reason_class=record.reason_class,
        reason_detail=(record.reason_detail[:500] if record.reason_detail is not None else None),
        is_output_guard=record.is_output_guard,
        action=record.action,
    )


def build_input_guard_totals(since: datetime, tenant_id: str | None = None) -> Any:
    query = (
        select(
            MetricGuardEvent.action.label("action"),
            func.count().label("count"),
        )
        .where(MetricGuardEvent.time >= since, MetricGuardEvent.is_output_guard.is_(False))
        .group_by(MetricGuardEvent.action)
    )
    if tenant_id is not None:
        query = query.where(MetricGuardEvent.tenant_id == tenant_id)
    return query


def build_input_guard_stage_counts(since: datetime, tenant_id: str | None = None) -> Any:
    query = (
        select(
            MetricGuardEvent.stage.label("stage"),
            MetricGuardEvent.action.label("action"),
            func.count().label("count"),
        )
        .where(MetricGuardEvent.time >= since, MetricGuardEvent.is_output_guard.is_(False))
        .group_by(MetricGuardEvent.stage, MetricGuardEvent.action)
    )
    if tenant_id is not None:
        query = query.where(MetricGuardEvent.tenant_id == tenant_id)
    return query


def build_input_guard_top_reasons(
    since: datetime,
    *,
    stage: str,
    tenant_id: str | None = None,
    limit: int = 5,
) -> Any:
    reason = func.coalesce(MetricGuardEvent.reason_class, MetricGuardEvent.reason_detail).label(
        "reason"
    )
    query = (
        select(reason, func.count().label("count"))
        .where(
            MetricGuardEvent.time >= since,
            MetricGuardEvent.is_output_guard.is_(False),
            MetricGuardEvent.stage == stage,
            MetricGuardEvent.action == REJECTED_ACTION,
            (MetricGuardEvent.reason_class.is_not(None))
            | (MetricGuardEvent.reason_detail.is_not(None)),
        )
        .group_by(reason)
        .order_by(func.count().desc())
        .limit(limit)
    )
    if tenant_id is not None:
        query = query.where(MetricGuardEvent.tenant_id == tenant_id)
    return query


def build_input_guard_audit_query(
    *,
    limit: int,
    tenant_id: str | None = None,
    action: str | None = None,
) -> Any:
    query = (
        select(
            MetricGuardEvent.id.label("id"),
            MetricGuardEvent.time.label("time"),
            MetricGuardEvent.tenant_id.label("tenant_id"),
            MetricGuardEvent.user_id.label("user_id"),
            MetricGuardEvent.channel.label("channel"),
            MetricGuardEvent.stage.label("stage"),
            MetricGuardEvent.category.label("category"),
            MetricGuardEvent.reason_class.label("reason_class"),
            MetricGuardEvent.reason_detail.label("reason_detail"),
            MetricGuardEvent.action.label("action"),
        )
        .where(MetricGuardEvent.is_output_guard.is_(False))
        .order_by(MetricGuardEvent.time.desc(), MetricGuardEvent.id.desc())
        .limit(max(1, min(limit, 500)))
    )
    if tenant_id is not None:
        query = query.where(MetricGuardEvent.tenant_id == tenant_id)
    if action:
        query = query.where(MetricGuardEvent.action == action)
    return query


def totals_from_rows(rows: Sequence[Mapping[Any, Any]]) -> dict[str, int]:
    totals = {ALLOWED_ACTION: 0, REJECTED_ACTION: 0, ERROR_ACTION: 0}
    for row in rows:
        action = str(row["action"] or "")
        if action in totals:
            totals[action] = int(row["count"] or 0)
    return totals


def stage_stats(
    stage: str,
    actions: dict[str, int],
    reason_rows: Sequence[Mapping[Any, Any]],
) -> dict[str, object]:
    allowed = actions.get(ALLOWED_ACTION, 0)
    rejected = actions.get(REJECTED_ACTION, 0)
    errors = actions.get(ERROR_ACTION, 0)
    return {
        "stage": stage,
        "triggered": allowed + rejected + errors,
        "allowed": allowed,
        "rejected": rejected,
        "errors": errors,
        "topReasons": [
            {"reason": str(row["reason"] or "unknown"), "count": int(row["count"] or 0)}
            for row in reason_rows
        ],
    }
