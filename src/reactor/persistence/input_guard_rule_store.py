from __future__ import annotations

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reactor.guards.rules import InputGuardRuleRecord, PatternType, RuleAction
from reactor.persistence.models import InputGuardRule


class SqlAlchemyInputGuardRuleStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def find_all(self, *, tenant_id: str) -> list[InputGuardRuleRecord]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_input_guard_rule_list(tenant_id=tenant_id))
            return [input_guard_rule_from_model(row) for row in rows]

    async def find_by_id(self, *, tenant_id: str, rule_id: str) -> InputGuardRuleRecord | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(InputGuardRule).where(
                    InputGuardRule.tenant_id == tenant_id,
                    InputGuardRule.id == rule_id,
                )
            )
            return input_guard_rule_from_model(row) if row is not None else None

    async def save(self, rule: InputGuardRuleRecord) -> InputGuardRuleRecord:
        rule.validate()
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.scalar(build_input_guard_rule_upsert(rule))
                if row is None:
                    raise RuntimeError("input guard rule upsert did not return a row")
                return input_guard_rule_from_model(row)

    async def update(
        self,
        *,
        tenant_id: str,
        rule_id: str,
        rule: InputGuardRuleRecord,
    ) -> InputGuardRuleRecord | None:
        rule.validate()
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.scalar(
                    build_input_guard_rule_update(tenant_id=tenant_id, rule_id=rule_id, rule=rule)
                )
                return input_guard_rule_from_model(row) if row is not None else None

    async def delete(self, *, tenant_id: str, rule_id: str) -> bool:
        async with self._session_factory() as session:
            async with session.begin():
                existing = await session.scalar(
                    select(InputGuardRule.id).where(
                        InputGuardRule.tenant_id == tenant_id,
                        InputGuardRule.id == rule_id,
                    )
                )
                if existing is None:
                    return False
                await session.execute(
                    delete(InputGuardRule).where(
                        InputGuardRule.tenant_id == tenant_id,
                        InputGuardRule.id == rule_id,
                    )
                )
                return True


def build_input_guard_rule_list(*, tenant_id: str):
    return (
        select(InputGuardRule)
        .where(InputGuardRule.tenant_id == tenant_id)
        .order_by(InputGuardRule.priority.desc(), InputGuardRule.created_at.asc())
    )


def build_input_guard_rule_upsert(rule: InputGuardRuleRecord):
    return (
        insert(InputGuardRule)
        .values(input_guard_rule_values(rule))
        .on_conflict_do_update(
            index_elements=[InputGuardRule.id],
            set_=input_guard_rule_values(rule, include_created_at=False),
        )
        .returning(InputGuardRule)
    )


def build_input_guard_rule_update(
    *,
    tenant_id: str,
    rule_id: str,
    rule: InputGuardRuleRecord,
):
    return (
        update(InputGuardRule)
        .where(InputGuardRule.tenant_id == tenant_id, InputGuardRule.id == rule_id)
        .values(input_guard_rule_values(rule, include_created_at=False, include_id=False))
        .returning(InputGuardRule)
    )


def input_guard_rule_values(
    rule: InputGuardRuleRecord,
    *,
    include_created_at: bool = True,
    include_id: bool = True,
) -> dict[str, object]:
    values: dict[str, object] = {
        "tenant_id": rule.tenant_id,
        "name": rule.name,
        "pattern": rule.pattern,
        "pattern_type": rule.pattern_type.value,
        "action": rule.action.value,
        "priority": rule.priority,
        "category": rule.category,
        "description": rule.description,
        "enabled": rule.enabled,
        "updated_at": rule.updated_at,
    }
    if include_id:
        values["id"] = rule.id
    if include_created_at:
        values["created_at"] = rule.created_at
    return values


def input_guard_rule_from_model(row: InputGuardRule) -> InputGuardRuleRecord:
    return InputGuardRuleRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        name=row.name,
        pattern=row.pattern,
        pattern_type=PatternType(row.pattern_type),
        action=RuleAction(row.action),
        priority=row.priority,
        category=row.category,
        description=row.description,
        enabled=row.enabled,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
