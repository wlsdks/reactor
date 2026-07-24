from __future__ import annotations

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reactor.guards.output_rules import (
    OutputGuardRuleAction,
    OutputGuardRuleAuditAction,
    OutputGuardRuleAuditRecord,
    OutputGuardRuleRecord,
)
from reactor.persistence.models import OutputGuardRule, OutputGuardRuleAudit


class SqlAlchemyOutputGuardRuleStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list(
        self, *, tenant_id: str, include_disabled: bool = True
    ) -> list[OutputGuardRuleRecord]:
        async with self._session_factory() as session:
            statement = build_output_guard_rule_list(
                tenant_id=tenant_id, include_disabled=include_disabled
            )
            rows = await session.scalars(statement)
            return [output_guard_rule_from_model(row) for row in rows]

    async def find_by_id(self, *, tenant_id: str, rule_id: str) -> OutputGuardRuleRecord | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(OutputGuardRule).where(
                    OutputGuardRule.tenant_id == tenant_id,
                    OutputGuardRule.id == rule_id,
                )
            )
            return output_guard_rule_from_model(row) if row is not None else None

    async def save(self, rule: OutputGuardRuleRecord) -> OutputGuardRuleRecord:
        rule.validate()
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.scalar(build_output_guard_rule_upsert(rule))
                if row is None:
                    raise RuntimeError("output guard rule upsert did not return a row")
                return output_guard_rule_from_model(row)

    async def update(
        self,
        *,
        tenant_id: str,
        rule_id: str,
        rule: OutputGuardRuleRecord,
    ) -> OutputGuardRuleRecord | None:
        rule.validate()
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.scalar(
                    build_output_guard_rule_update(
                        tenant_id=tenant_id,
                        rule_id=rule_id,
                        rule=rule,
                    )
                )
                return output_guard_rule_from_model(row) if row is not None else None

    async def delete(self, *, tenant_id: str, rule_id: str) -> bool:
        async with self._session_factory() as session:
            async with session.begin():
                existing = await session.scalar(
                    select(OutputGuardRule.id).where(
                        OutputGuardRule.tenant_id == tenant_id,
                        OutputGuardRule.id == rule_id,
                    )
                )
                if existing is None:
                    return False
                await session.execute(
                    delete(OutputGuardRule).where(
                        OutputGuardRule.tenant_id == tenant_id,
                        OutputGuardRule.id == rule_id,
                    )
                )
                return True


class SqlAlchemyOutputGuardRuleAuditStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list(self, *, tenant_id: str, limit: int = 100) -> list[OutputGuardRuleAuditRecord]:
        async with self._session_factory() as session:
            rows = await session.scalars(
                select(OutputGuardRuleAudit)
                .where(OutputGuardRuleAudit.tenant_id == tenant_id)
                .order_by(OutputGuardRuleAudit.created_at.desc())
                .limit(max(1, min(limit, 1000)))
            )
            return [output_guard_audit_from_model(row) for row in rows]

    async def save(self, audit: OutputGuardRuleAuditRecord) -> OutputGuardRuleAuditRecord:
        async with self._session_factory() as session:
            async with session.begin():
                row = OutputGuardRuleAudit(
                    id=audit.id,
                    tenant_id=audit.tenant_id,
                    rule_id=audit.rule_id,
                    action=audit.action.value,
                    actor=audit.actor,
                    detail=audit.detail,
                    created_at=audit.created_at,
                )
                session.add(row)
            return audit


def build_output_guard_rule_list(*, tenant_id: str, include_disabled: bool = True):
    statement = select(OutputGuardRule).where(OutputGuardRule.tenant_id == tenant_id)
    if not include_disabled:
        statement = statement.where(OutputGuardRule.enabled.is_(True))
    return statement.order_by(
        OutputGuardRule.priority.asc(),
        OutputGuardRule.created_at.asc(),
        OutputGuardRule.id.asc(),
    )


def build_output_guard_rule_upsert(rule: OutputGuardRuleRecord):
    return (
        insert(OutputGuardRule)
        .values(output_guard_rule_values(rule))
        .on_conflict_do_update(
            index_elements=[OutputGuardRule.id],
            set_=output_guard_rule_values(rule, include_created_at=False),
        )
        .returning(OutputGuardRule)
    )


def build_output_guard_rule_update(
    *,
    tenant_id: str,
    rule_id: str,
    rule: OutputGuardRuleRecord,
):
    return (
        update(OutputGuardRule)
        .where(OutputGuardRule.tenant_id == tenant_id, OutputGuardRule.id == rule_id)
        .values(output_guard_rule_values(rule, include_created_at=False, include_id=False))
        .returning(OutputGuardRule)
    )


def output_guard_rule_values(
    rule: OutputGuardRuleRecord,
    *,
    include_created_at: bool = True,
    include_id: bool = True,
) -> dict[str, object]:
    values: dict[str, object] = {
        "tenant_id": rule.tenant_id,
        "name": rule.name,
        "pattern": rule.pattern,
        "action": rule.action.value,
        "replacement": rule.replacement,
        "priority": rule.priority,
        "enabled": rule.enabled,
        "updated_at": rule.updated_at,
    }
    if include_id:
        values["id"] = rule.id
    if include_created_at:
        values["created_at"] = rule.created_at
    return values


def output_guard_rule_from_model(row: OutputGuardRule) -> OutputGuardRuleRecord:
    return OutputGuardRuleRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        name=row.name,
        pattern=row.pattern,
        action=OutputGuardRuleAction(row.action),
        replacement=row.replacement,
        priority=row.priority,
        enabled=row.enabled,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def output_guard_audit_from_model(row: OutputGuardRuleAudit) -> OutputGuardRuleAuditRecord:
    return OutputGuardRuleAuditRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        rule_id=row.rule_id,
        action=OutputGuardRuleAuditAction(row.action),
        actor=row.actor,
        detail=row.detail,
        created_at=row.created_at,
    )
