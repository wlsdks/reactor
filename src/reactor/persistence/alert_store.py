from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reactor.observability.alerts import (
    AlertInstance,
    AlertRule,
    AlertSeverity,
    AlertStatus,
    AlertType,
    Baseline,
    ErrorBudget,
)
from reactor.persistence.models import AlertInstanceRow, AlertRuleRow


class SqlAlchemyAlertRuleStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def find_rules_for_tenant(self, tenant_id: str) -> list[AlertRule]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_alert_rule_list(tenant_id=tenant_id))
        return [alert_rule_from_row(row) for row in rows]

    async def find_platform_rules(self) -> list[AlertRule]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_alert_rule_list(platform_only=True))
        return [alert_rule_from_row(row) for row in rows]

    async def find_all_rules(self) -> list[AlertRule]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_alert_rule_list())
        return [alert_rule_from_row(row) for row in rows]

    async def save_rule(self, rule: AlertRule) -> AlertRule:
        rule.validate()
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.scalar(build_alert_rule_upsert(rule))
                if row is None:
                    raise RuntimeError("alert rule upsert did not return a row")
        return alert_rule_from_row(row)

    async def delete_rule(self, rule_id: str, *, tenant_id: str | None = None) -> bool:
        async with self._session_factory() as session:
            async with session.begin():
                deleted_id = await session.scalar(
                    build_alert_rule_delete(rule_id, tenant_id=tenant_id)
                )
        return deleted_id is not None

    async def find_active_alerts(self, tenant_id: str | None = None) -> list[AlertInstance]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_alert_active_list(tenant_id=tenant_id))
        return [alert_instance_from_row(row) for row in rows]

    async def save_alert(self, alert: AlertInstance) -> AlertInstance:
        alert.validate()
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.scalar(build_alert_save(alert))
                if row is None:
                    raise RuntimeError("alert insert did not return a row")
        return alert_instance_from_row(row)

    async def resolve_alert(
        self,
        alert_id: str,
        *,
        tenant_id: str | None = None,
        actor: str | None = None,
    ) -> bool:
        async with self._session_factory() as session:
            async with session.begin():
                resolved_id = await session.scalar(
                    build_alert_resolve(
                        alert_id,
                        tenant_id=tenant_id,
                        actor=actor,
                        at=datetime.now(UTC),
                    )
                )
        return resolved_id is not None

    def metric_value(self, rule: AlertRule) -> float | None:
        del rule
        return None

    def baseline(self, tenant_id: str, metric: str) -> Baseline | None:
        del tenant_id, metric
        return None

    def error_budget(self, tenant_id: str) -> ErrorBudget | None:
        del tenant_id
        return None


def build_alert_rule_list(
    *, tenant_id: str | None = None, platform_only: bool | None = None
) -> Any:
    statement = select(AlertRuleRow)
    if tenant_id is not None:
        statement = statement.where(AlertRuleRow.tenant_id == tenant_id)
    if platform_only is True:
        statement = statement.where(
            (AlertRuleRow.tenant_id.is_(None)) | (AlertRuleRow.platform_only.is_(True))
        )
    return statement.order_by(AlertRuleRow.created_at.asc())


def build_alert_rule_upsert(rule: AlertRule) -> Any:
    rule.validate()
    return (
        insert(AlertRuleRow)
        .values(alert_rule_values(rule))
        .on_conflict_do_update(
            index_elements=[AlertRuleRow.id],
            set_=alert_rule_values(rule),
        )
        .returning(AlertRuleRow)
    )


def build_alert_rule_delete(rule_id: str, *, tenant_id: str | None = None) -> Any:
    statement = delete(AlertRuleRow).where(AlertRuleRow.id == rule_id)
    if tenant_id is not None:
        statement = statement.where(AlertRuleRow.tenant_id == tenant_id)
    return statement.returning(AlertRuleRow.id)


def build_alert_save(alert: AlertInstance) -> Any:
    alert.validate()
    return insert(AlertInstanceRow).values(alert_values(alert)).returning(AlertInstanceRow)


def build_alert_active_list(tenant_id: str | None = None) -> Any:
    statement = select(AlertInstanceRow).where(AlertInstanceRow.status == AlertStatus.ACTIVE.value)
    if tenant_id is not None:
        statement = statement.where(AlertInstanceRow.tenant_id == tenant_id)
    return statement.order_by(AlertInstanceRow.fired_at.asc())


def build_alert_resolve(
    alert_id: str,
    *,
    tenant_id: str | None = None,
    actor: str | None,
    at: datetime,
) -> Any:
    statement = update(AlertInstanceRow).where(AlertInstanceRow.id == alert_id)
    if tenant_id is not None:
        statement = statement.where(AlertInstanceRow.tenant_id == tenant_id)
    return statement.values(
        status=AlertStatus.RESOLVED.value,
        resolved_at=at,
        acknowledged_by=actor,
    ).returning(AlertInstanceRow.id)


def alert_rule_values(rule: AlertRule) -> dict[str, object]:
    return {
        "id": rule.id,
        "tenant_id": rule.tenant_id,
        "name": rule.name,
        "description": rule.description,
        "type": rule.type.value,
        "severity": rule.severity.value,
        "metric": rule.metric,
        "threshold": rule.threshold,
        "window_minutes": rule.window_minutes,
        "enabled": rule.enabled,
        "platform_only": rule.platform_only,
        "created_at": rule.created_at,
    }


def alert_values(alert: AlertInstance) -> dict[str, object]:
    return {
        "id": alert.id,
        "rule_id": alert.rule_id,
        "tenant_id": alert.tenant_id,
        "severity": alert.severity.value,
        "status": alert.status.value,
        "message": alert.message,
        "metric_value": alert.metric_value,
        "threshold": alert.threshold,
        "fired_at": alert.fired_at,
        "resolved_at": alert.resolved_at,
        "acknowledged_by": alert.acknowledged_by,
    }


def alert_rule_from_row(row: AlertRuleRow) -> AlertRule:
    return AlertRule(
        id=row.id,
        tenant_id=row.tenant_id,
        name=row.name,
        description=row.description,
        type=AlertType(row.type),
        severity=AlertSeverity(row.severity),
        metric=row.metric,
        threshold=row.threshold,
        window_minutes=row.window_minutes,
        enabled=row.enabled,
        platform_only=row.platform_only,
        created_at=row.created_at,
    )


def alert_instance_from_row(row: AlertInstanceRow) -> AlertInstance:
    return AlertInstance(
        id=row.id,
        rule_id=row.rule_id,
        tenant_id=row.tenant_id,
        severity=AlertSeverity(row.severity),
        status=AlertStatus(row.status),
        message=row.message,
        metric_value=row.metric_value,
        threshold=row.threshold,
        fired_at=row.fired_at,
        resolved_at=row.resolved_at,
        acknowledged_by=row.acknowledged_by,
    )
